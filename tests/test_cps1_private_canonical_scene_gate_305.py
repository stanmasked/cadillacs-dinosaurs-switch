"""Stage305 synthetic-only fail-closed original-gfx/synthetic-scene gate tests."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tools import cps1_private_canonical_scene_gate_305 as gate
from tools import cps1_private_scene_compositor_parity as scene
from tools import mame0106_private_dino_rom_canonicalize_299 as canonical


def fabricated_native():
    """Only aggregate invented scene statistics; never original media."""
    out = scene._status("PRIVATE_NATIVE_SCENE_PARITY_PASSED")
    out.update({
        "scene_size": [scene.WIDTH, scene.HEIGHT],
        "synthetic_cases": len(scene.CASES),
        "pixels_compared": len(scene.CASES) * scene.PIXELS,
        "mismatching_pixels_total": 0,
        "differential_inputs_verified": True,
        "differential_coverage_verified": True,
        "scenario_results": [
            {"scenario": name, "compared_rgba_pixels": scene.PIXELS,
             "mismatching_rgba_pixels": 0}
            for name in scene.CASES
        ],
    })
    for key, should_change in scene.DIFFERENTIAL_EXPECTATIONS.items():
        out[key] = 61 if should_change else 0
    return out


class CanonicalSceneGate305Tests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="dino305-no-rom-data-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.rom = self.root / "artificial-private.zip"
        self.rom.write_bytes(b"ARTIFICIAL BYTE STRING; NO GAME ASSETS")
        self.native = fabricated_native()
        self.compositor_calls = 0

    def rom_verify(self, path, *, manifest):
        self.assertEqual(Path(path), self.rom)
        self.assertIs(manifest, canonical.MANIFEST)
        return {
            "status": canonical.MATCH,
            "required_rom_members_matched_by_crc32_sha1": len(manifest),
            "required_payloads_crc_sha1_integrity_checked": True,
        }

    def fake_scene(self, path):
        self.assertEqual(Path(path), self.rom)
        self.compositor_calls += 1
        return copy.deepcopy(self.native)

    def run_checked(self):
        return gate.run(self.rom, verify=self.rom_verify,
                        compositor=self.fake_scene)

    def test_all_fourteen_synthetic_scenes_pass_exact_c_python_contract(self):
        r = self.run_checked()
        self.assertEqual(r["status"], gate.PASS)
        self.assertEqual(r["original_rom_member_count"], 16)
        self.assertEqual(r["synthetic_scene_cases_checked"], 14)
        self.assertEqual(r["synthetic_scene_rgba_pixels_compared"],
                         14 * 384 * 224)
        self.assertEqual(r["c_python_mismatching_rgba_pixels"], 0)
        self.assertTrue(r["synthetic_priority_and_palette_metamorphic_checks_passed"])
        self.assertEqual(self.compositor_calls, 1)
        self.assertNotIn(str(self.root), json.dumps(r))

    def test_true_source_rom_hashes_are_mandatory_before_compositor_runs(self):
        def false_hash(_path, *, manifest):
            return {"status": canonical.MATCH,
                    "required_rom_members_matched_by_crc32_sha1": len(manifest)}
        result = gate.run(self.rom, verify=false_hash,
                          compositor=self.fake_scene)
        self.assertEqual(result["status"], gate.BLOCKED_ROM)
        self.assertFalse(result["original_cps1_rom_source_crc32_sha1_verified"])
        self.assertEqual(self.compositor_calls, 0)

    def test_incomplete_source_rom_count_rejected(self):
        def partial(_p, *, manifest):
            return {"status": canonical.MATCH,
                    "required_rom_members_matched_by_crc32_sha1": len(manifest)-1,
                    "required_payloads_crc_sha1_integrity_checked": True}
        result = gate.run(self.rom, verify=partial,
                          compositor=self.fake_scene)
        self.assertEqual(result["status"], gate.BLOCKED_ROM)
        self.assertFalse(result["original_game_frame_captured"])
        self.assertEqual(self.compositor_calls, 0)

    def test_false_positive_native_status_not_accepted(self):
        self.native["status"] = "PRIVATE_NATIVE_SCENE_PARITY_MISMATCH"
        result = self.run_checked()
        self.assertEqual(result["status"], gate.BLOCKED_SCENE)
        self.assertTrue(result["original_cps1_rom_source_crc32_sha1_verified"])
        self.assertEqual(result["synthetic_scene_cases_checked"], 0)

    def test_missing_scenario_cannot_claim_full_scene_coverage(self):
        self.native["scenario_results"].pop()
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)

    def test_duplicate_or_reordered_synthetic_scene_names_rejected(self):
        self.native["scenario_results"][1]["scenario"] = scene.CASES[0]
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)
        self.native = fabricated_native()
        self.native["scenario_results"].reverse()
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)

    def test_single_pixel_mismatch_cannot_claim_success(self):
        self.native["scenario_results"][3]["mismatching_rgba_pixels"] = 1
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)
        self.native = fabricated_native()
        self.native["mismatching_pixels_total"] = 1
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)

    def test_shortened_scene_dimensions_or_total_pixels_rejected(self):
        self.native["scene_size"] = [384, 223]
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)
        self.native = fabricated_native()
        self.native["pixels_compared"] = 14 * scene.PIXELS - 1
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)
        self.native = fabricated_native()
        self.native["scenario_results"][0]["compared_rgba_pixels"] -= 1
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)

    def test_differential_evidence_must_advance_when_required(self):
        name = next(key for key, value
                    in scene.DIFFERENTIAL_EXPECTATIONS.items() if value)
        self.native[name] = 0
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)

    def test_transparent_palette_and_pen_fifteen_must_be_invariant(self):
        zero = next(key for key, value
                    in scene.DIFFERENTIAL_EXPECTATIONS.items() if not value)
        self.native[zero] = 1
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)

    def test_missing_or_boolean_differential_count_rejected(self):
        key = next(iter(scene.DIFFERENTIAL_EXPECTATIONS))
        del self.native[key]
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)
        self.native = fabricated_native()
        self.native[key] = True
        self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)

    def test_gameplay_or_switch_provenance_cannot_be_forged(self):
        for flag in ("original_game_frame_captured",
                     "real_gameplay_observed",
                     "mame_vblank_synchronization_verified",
                     "sprite_latch_timing_verified",
                     "nintendo_switch_framebuffer_parity_verified",
                     "source_rom_or_derived_pixel_bytes_written_to_disk",
                     "private_paths_or_game_digests_in_report"):
            with self.subTest(flag=flag):
                self.native = fabricated_native()
                self.native[flag] = True
                self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)
        for name in ("background_tile_graphics_from_original_rom",
                     "palette_scroll_obj_and_priority_are_synthetic",
                     "diagnostic_only", "differential_inputs_verified",
                     "differential_coverage_verified"):
            with self.subTest(name=name):
                self.native = fabricated_native()
                self.native[name] = False
                self.assertEqual(self.run_checked()["status"], gate.BLOCKED_SCENE)

    def test_symlinked_private_rom_not_used(self):
        link = self.root / "symlink.zip"
        link.symlink_to(self.rom)
        with self.assertRaises(ValueError):
            gate.run(link, verify=self.rom_verify,
                     compositor=self.fake_scene)
        self.assertEqual(self.compositor_calls, 0)

    def test_private_cli_failure_redacts_exception_and_original_path(self):
        out = self.root / "exclusive-receipt.json"
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = gate.main(["--rom", str(self.rom), "--out", str(out)])
        self.assertEqual(rc, 2)  # fixture is not a genuine source-hashed ROM
        self.assertEqual(json.loads(out.read_text())["status"],
                         gate.BLOCKED_SETUP)
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), stdout.getvalue())
        self.assertNotIn(str(self.root), out.read_text())
        self.assertFalse(json.loads(out.read_text())["original_game_frame_captured"])

    def test_aggregate_report_explicitly_rejects_real_gameplay_claim(self):
        result = self.run_checked()
        for name in (
            "actual_gameplay_palette_or_vram_verified",
            "original_game_frame_captured",
            "original_dino_mame_execution_verified",
            "original_dino_inp_wlf_replay_verified",
            "original_gameplay_equivalence_verified",
            "real_nintendo_switch_framebuffer_verified",
            "original_rom_images_hashes_or_paths_exported",
        ):
            self.assertIs(result[name], False)


if __name__ == "__main__":
    unittest.main()

"""Stage317 ROM-free C/Python evidence gates: never use original game ROMs."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools import cps1_private_original_scene_preflight_317 as stage
from tools import cps1_private_canonical_scene_gate_305 as ref


def valid_stage305():
    return {
        "schema":ref.SCHEMA,
        "status":ref.PASS,
        "original_cps1_rom_source_crc32_sha1_verified":True,
        "original_rom_member_count":16,
        "synthetic_scene_cases_checked":14,
        "synthetic_scene_rgba_pixels_compared":stage.PIXELS,
        "c_python_mismatching_rgba_pixels":0,
        "synthetic_priority_and_palette_metamorphic_checks_passed":True,
        "actual_gameplay_palette_or_vram_verified":False,
        "original_game_frame_captured":False,
        "original_dino_mame_execution_verified":False,
        "original_dino_inp_wlf_replay_verified":False,
        "original_gameplay_equivalence_verified":False,
        "real_nintendo_switch_framebuffer_verified":False,
        "original_rom_images_hashes_or_paths_exported":False,
    }


class Stage317NativeRealGfxSafety(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory(prefix="stage317-invented-only-")
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.rom=self.root/"dino.zip"
        self.rom.write_bytes(b"NOT A ROM")
        self.sd=self.root/"private-sd"
        self.sd.mkdir()
        self.example=b"A"*stage.stage315.GFX_BYTES

    def good(self,**kwargs):
        return stage.run(self.rom,self.sd,
            c_python_gate=kwargs.get("c_python_gate",lambda _:valid_stage305()),
            sd_gate=kwargs.get("sd_gate",lambda _a,_b:self.example))

    def test_strict_mock_contract_not_real_guest(self):
        summary=self.good()
        self.assertEqual(summary["status"],stage.PASS)
        self.assertEqual(summary["native_c_python_rgba_pixels_matched"],1204224)
        self.assertEqual(summary["verified_original_rom_members"],16)
        self.assertFalse(summary["original_graphics_host_x11_display_verified"])
        self.assertFalse(summary["original_game_mame_execution_verified"])
        self.assertFalse(summary["physical_nintendo_switch_display_verified"])

    def test_unverified_sd_fails_before_native_c(self):
        calls=[]
        def bogus_c(_):
            calls.append("native")
            return valid_stage305()
        with self.assertRaises(ValueError):
            self.good(sd_gate=lambda _a,_b:None,c_python_gate=bogus_c)
        self.assertEqual(calls,[])

    def test_required_scene_keys_and_boolean_counts(self):
        x=valid_stage305()
        for key in x:
            with self.subTest(missing=key):
                y=dict(x);del y[key]
                with self.assertRaises(ValueError):
                    stage.validate_stage305(y)
        for key in ("original_rom_member_count","synthetic_scene_cases_checked",
                    "synthetic_scene_rgba_pixels_compared","c_python_mismatching_rgba_pixels"):
            y=dict(x);y[key]=True
            with self.subTest(bool_integer=key),self.assertRaises(ValueError):
                stage.validate_stage305(y)

    def test_any_native_pixel_mismatch_rejected(self):
        y=valid_stage305();y["c_python_mismatching_rgba_pixels"]=1
        with self.assertRaises(ValueError):
            self.good(c_python_gate=lambda _:y)

    def test_partial_original_rom_source_gate_rejected(self):
        for key,value in (
            ("original_cps1_rom_source_crc32_sha1_verified",False),
            ("original_rom_member_count",15),
            ("original_rom_images_hashes_or_paths_exported",True),
        ):
            y=valid_stage305();y[key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):
                self.good(c_python_gate=lambda _:y)

    def test_no_false_gameplay_or_console_provenance(self):
        original=valid_stage305()
        for key in (
            "actual_gameplay_palette_or_vram_verified",
            "original_game_frame_captured",
            "original_dino_mame_execution_verified",
            "original_dino_inp_wlf_replay_verified",
            "original_gameplay_equivalence_verified",
            "real_nintendo_switch_framebuffer_verified",
        ):
            y=dict(original);y[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.good(c_python_gate=lambda _:y)

    def test_bad_gfx_size_refused(self):
        with self.assertRaises(ValueError):
            self.good(sd_gate=lambda _a,_b:self.example[:-1])
        with self.assertRaises(ValueError):
            self.good(sd_gate=lambda _a,_b:bytearray(self.example))

    def test_cli_blocks_dummy_rom_and_writes_private_redacted_receipt(self):
        out=self.root/"blocked.json"
        stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc=stage.main(["--rom",str(self.rom),"--sd-root",str(self.sd),
                           "--out",str(out)])
        self.assertEqual(rc,2)
        self.assertEqual(stdout.getvalue().strip(),stage.BLOCKED)
        receipt=json.loads(out.read_text())
        self.assertEqual(out.stat().st_mode&0o777,0o600)
        self.assertNotIn(str(self.root),json.dumps(receipt))
        self.assertFalse(receipt["private_original_pixels_paths_hashes_or_assets_exported"])

    def test_output_inside_public_repository_refused(self):
        root=Path(__file__).resolve().parents[1]
        out=root/"stage317-no-private-asset.json"
        with contextlib.redirect_stdout(io.StringIO()):
            rc=stage.main(["--rom",str(self.rom),"--sd-root",str(self.sd),
                           "--out",str(out)])
        self.assertEqual(rc,2)
        self.assertFalse(out.exists())

    def test_duplicate_receipt_refuses_overwrite(self):
        out=self.root/"receipt.json"
        out.write_text("UNTOUCHED")
        stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc=stage.main(["--rom",str(self.rom),"--sd-root",str(self.sd),
                           "--out",str(out)])
        self.assertEqual(rc,2)
        self.assertEqual(out.read_text(),"UNTOUCHED")


if __name__=="__main__":
    unittest.main()

"""Stage306: synthetic-only exhaustive CPS1 C/Python pixel parity tests.

Uses 512 bytes of wholly invented graphics (not actual ROM, no screenshots)
and compiles the actual project's portable C tile decoder.
"""
import copy
import ctypes
import io
import json
import random
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tools import cps1_private_exhaustive_tiles_306 as audit
from tools import mame0106_private_dino_rom_canonicalize_299 as canon


class ExhaustiveCPS1Tiles306Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="dino306-synthetic-c-source-")
        cls.lib = Path(cls.tmp.name) / "fake-original-free.so"
        audit._compile_native(cls.lib)
        cls.native = ctypes.CDLL(str(cls.lib))
        rng = random.Random(42)
        cls.gfx = bytes(rng.randrange(256) for _ in range(512))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino306-no-game-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rom = self.root / "synthetic-placeholder.zip"
        self.rom.write_bytes(b"NO ACTUAL GAME OR IMAGE BYTES IN TEST")

    def test_exhaustive_three_sizes_on_invented_graphics(self):
        result = audit.compare_graphics(self.gfx, self.native)
        self.assertEqual(result["status"], audit.MATCH)
        self.assertEqual([x["tile_size"] for x in result["formats"]], [8,16,32])
        self.assertEqual([x["compared_tiles"] for x in result["formats"]], [16,4,1])
        self.assertEqual([x["compared_pen_indices"] for x in result["formats"]],
                         [1024,1024,1024])
        self.assertEqual(result["total_compared_tiles"],21)
        self.assertEqual(result["total_compared_pen_indices"],3072)
        self.assertEqual([x["distinct_pen_values"] for x in result["formats"]],
                         [16,16,16])
        self.assertTrue(result["all_8_16_32_tile_codes_and_8x8_halves_exhaustive"])
        self.assertFalse(result["mame_original_game_executed"])
        self.assertFalse(result["original_cps1_rom_source_crc32_sha1_verified"])

    def test_byte_identical_python_reference_matches_actual_portable_c(self):
        for side, codes in ((8,8),(16,4),(32,1)):
            for code in range(codes):
                for half in ((0,32) if side==8 else (0,)):
                    ref = audit._decode_python(self.gfx,side,code,half)
                    self.assertEqual(len(ref),side*side)
                    self.assertTrue(all(0 <= v <= 15 for v in ref))
        self.assertEqual(audit.compare_graphics(self.gfx,self.native)["status"],
                         audit.MATCH)

    def test_one_invented_pixel_reference_corruption_causes_mismatch(self):
        def altered(gfx, side, code, half=0):
            correct = bytearray(audit._decode_python(gfx,side,code,half))
            if side == 16 and code == 2:
                correct[5] ^= 1
            return bytes(correct)
        report = audit.compare_graphics(self.gfx,self.native,reference=altered)
        self.assertEqual(report["status"],audit.MISMATCH)
        self.assertEqual([x["mismatching_tiles"] for x in report["formats"]],[0,1,0])

    def test_false_reference_length_is_hard_failure(self):
        with self.assertRaisesRegex(ValueError,"reference"):
            audit.compare_graphics(self.gfx,self.native,
                                   reference=lambda *_: b"\x00")

    def test_reference_four_bit_palette_boundaries_are_enforced(self):
        def bogus(gfx,side,code,half=0):
            value = bytearray(audit._decode_python(gfx,side,code,half))
            value[0] = 16
            return bytes(value)
        with self.assertRaisesRegex(ValueError,"reference"):
            audit.compare_graphics(self.gfx,self.native,reference=bogus)

    def test_valid_but_flat_zero_image_is_not_treated_as_coverage(self):
        report = audit.compare_graphics(bytes(512),self.native)
        self.assertEqual(report["status"],audit.MISMATCH)
        self.assertEqual([x["mismatching_tiles"] for x in report["formats"]],
                         [0,0,0])
        self.assertEqual([x["distinct_pen_values"] for x in report["formats"]],
                         [1,1,1])

    def test_invalid_short_or_nonmultiple_region_refused(self):
        for invalid in (b"",b"\x00"*511,b"\x00"*513,b"\x00"*64,object()):
            with self.subTest(length=len(invalid) if isinstance(invalid,bytes) else "obj"):
                with self.assertRaises(ValueError):
                    audit.compare_graphics(invalid,self.native)

    def test_wrong_tile_index_and_oversized_code_refused(self):
        for args in ((8,0,1),(8,8,0),(16,4,0),(32,1,0),
                     (32,0,32),(64,0,0),(-1,0,0)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    audit._decode_python(self.gfx,*args)

    def test_real_provenance_is_never_claimed_from_synthetic_tiles(self):
        d = audit.compare_graphics(self.gfx,self.native)
        for key in ("mame_original_game_executed",
                    "real_mame_frame_or_palette_observed",
                    "original_inp_wlf_replay_verified",
                    "nintendo_switch_hardware_frame_verified",
                    "original_rom_or_derived_pixel_bytes_exported"):
            self.assertIs(d[key],False)
        self.assertNotIn(str(self.root),json.dumps(d))
        self.assertNotRegex(json.dumps(d), r"(?i)\b[0-9a-f]{40}\b")

    def test_private_gate_requires_complete_source_rom_hashes_before_compile(self):
        called=[]
        def fake_verify(path, *,manifest):
            return {"status":canon.MATCH,
                    "required_rom_members_matched_by_crc32_sha1":15,
                    "required_payloads_crc_sha1_integrity_checked":True}
        with self.assertRaisesRegex(ValueError,"source"):
            audit.private_audit(self.rom,verify=fake_verify,
                                load=lambda *_: called.append("load"))
        self.assertEqual(called,[])

    def test_private_gate_can_execute_whole_compiler_with_artificial_fixture(self):
        def verified(path,*,manifest):
            self.assertEqual(path,self.rom)
            return {"status":canon.MATCH,
                    "required_rom_members_matched_by_crc32_sha1":len(manifest),
                    "required_payloads_crc_sha1_integrity_checked":True}
        with mock.patch.object(audit,"EXPECTED_GFX_BYTES",512):
            result = audit.private_audit(
                self.rom,verify=verified,load=lambda _p:self.gfx)
        self.assertEqual(result["status"],audit.MATCH)
        self.assertTrue(result["original_cps1_rom_source_crc32_sha1_verified"])
        self.assertEqual(result["original_gfx_region_bytes"],512)
        self.assertFalse(result["mame_original_game_executed"])

    def test_symlinked_original_archive_disallowed(self):
        link=self.root/"private-symlink.zip"
        link.symlink_to(self.rom)
        with self.assertRaises(ValueError):
            audit.private_audit(link)

    def test_cli_refusal_sanitizes_paths_and_gameplay_evidence(self):
        output=self.root/"private-stage306.json"
        stdout=io.StringIO()
        with redirect_stdout(stdout):
            result=audit.main(["--rom",str(self.rom),"--out",str(output)])
        self.assertEqual(result,2)
        record=json.loads(output.read_text())
        self.assertEqual(record["status"],audit.BLOCKED)
        self.assertEqual(output.stat().st_mode & 0o777,0o600)
        self.assertFalse(record["mame_original_game_executed"])
        self.assertNotIn(str(self.root),stdout.getvalue())
        self.assertNotIn(str(self.root),output.read_text())

    def test_exhaustive_counts_are_consistent_across_tile_dimensions(self):
        report=audit.compare_graphics(self.gfx,self.native)
        self.assertEqual(len({row["compared_pen_indices"]
                             for row in report["formats"]}),1)
        self.assertEqual(sum(x["mismatching_tiles"] for x in report["formats"]),0)
        self.assertEqual(sum(x["native_decode_failures"] for x in report["formats"]),0)


if __name__=="__main__":
    unittest.main()

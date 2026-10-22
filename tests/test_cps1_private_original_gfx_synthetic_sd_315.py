"""Stage315: ONLY invented bytes in public CI; no copyrighted ROM."""
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest import TestCase, mock

from tools import cps1_private_original_gfx_synthetic_sd_315 as stage
from tools import mame0106_private_dino_rom_canonicalize_299 as canonical
from tools import cps1_synthetic_scene_sequence_307 as sequence
from tools import cps1_synthetic_gfx_fixture_308 as artificial


def fake_evidence():
    # This synthetic dictionary is never used to demonstrate a real ROM.
    return {
        "status": canonical.MATCH,
        "required_rom_members_matched_by_crc32_sha1": len(canonical.MANIFEST),
        "required_payloads_crc_sha1_integrity_checked": True,
        "canonical_mame_zip_written": False,
        "all_original_payload_bytes_kept_private": True,
        "actual_historical_mame_rom_loader_verified": False,
        "original_dino_gameplay_verified": False,
    }


class Stage315PrivateOriginalGfxWithSyntheticFrames(TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="dino315-no-rom-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.source=self.root/"dino.zip"
        self.source.write_bytes(b"NOT A REAL ROM ARCHIVE")
        self.output=self.root/"new-sd"
        self.invented=bytes(range(256))*(stage.GFX_BYTES//256)
        self.checked=0

    def verify(self,path,*,manifest):
        self.assertEqual(path,self.source)
        self.assertEqual(manifest,canonical.MANIFEST)
        self.checked+=1
        return fake_evidence()

    def load(self,path):
        self.assertEqual(self.checked,1)
        self.assertEqual(path,self.source)
        return self.invented

    def test_isolated_private_directory_contains_exactly_two_expected_files(self):
        report=stage.stage(self.source,self.output,verify=self.verify,load=self.load)
        self.assertEqual(report["status"],stage.PASS)
        target=self.output/stage.APP
        self.assertEqual(set(p.name for p in target.iterdir()),
                         {"gfx.bin","sequence.bin"})
        self.assertEqual((target/"gfx.bin").read_bytes(),self.invented)
        seq,_=sequence.build(fps=2)
        self.assertEqual((target/"sequence.bin").read_bytes(),seq)
        self.assertEqual((target/"gfx.bin").stat().st_mode&0o777,0o600)
        self.assertEqual((target/"sequence.bin").stat().st_mode&0o777,0o600)
        self.assertEqual(self.output.stat().st_mode&0o777,0o700)
        self.assertEqual((self.output/"switch").stat().st_mode&0o777,0o700)
        self.assertEqual(target.stat().st_mode&0o777,0o700)
        self.assertEqual((self.output/stage.RECEIPT).stat().st_mode&0o777,0o600)

    def test_no_private_derived_data_or_digests_in_receipt(self):
        report=stage.stage(self.source,self.output,verify=self.verify,load=self.load)
        self.assertEqual(report, json.loads((self.output/stage.RECEIPT).read_text()))
        self.assertTrue(report["original_graphics_are_from_source_verified_rom"])
        self.assertTrue(report["palette_scroll_obj_priority_are_synthetic"])
        for field in (
            "actual_mame_gameplay_executed","original_gameplay_vram_palette_observed",
            "original_game_frames_captured","original_inp_wlf_replay_verified",
            "nexium_original_gfx_guest_run_verified",
            "physical_nintendo_switch_display_verified",
            "original_graphics_or_hashes_in_public_artifacts",
            "private_paths_in_report",
        ):
            self.assertIs(report[field],False)
        serialized=json.dumps(report)
        self.assertNotIn(str(self.root),serialized)
        self.assertNotIn(self.source.name,serialized)
        self.assertNotIn(stage._digest_bytes(self.invented).hex(),serialized)
        self.assertNotIn(self.invented[:16].hex(),serialized)

    def test_rejected_archive_has_no_output_side_effects(self):
        def rejected(path,*,manifest):
            evidence=fake_evidence()
            evidence["status"]=canonical.BLOCKED
            return evidence
        with self.assertRaises(ValueError):
            stage.stage(self.source,self.output,verify=rejected,load=self.load)
        self.assertFalse(self.output.exists())

    def test_verify_runs_before_original_bytes_are_decoded(self):
        called=[]
        def rejected(path,*,manifest):
            return {**fake_evidence(),
                    "required_rom_members_matched_by_crc32_sha1":15}
        with self.assertRaises(ValueError):
            stage.stage(self.source,self.output,verify=rejected,
                        load=lambda path:called.append(path))
        self.assertEqual(called,[])
        self.assertFalse(self.output.exists())

    def test_wrong_evidence_fields_and_boolean_count_rejected(self):
        for key,bad in (
            ("required_rom_members_matched_by_crc32_sha1",True),
            ("required_payloads_crc_sha1_integrity_checked",False),
            ("canonical_mame_zip_written",True),
            ("all_original_payload_bytes_kept_private",False),
            ("actual_historical_mame_rom_loader_verified",True),
            ("original_dino_gameplay_verified",True),
        ):
            with self.subTest(key=key):
                record=fake_evidence()
                record[key]=bad
                self.assertFalse(stage._validate_rom_evidence(record))
        self.assertFalse(stage._validate_rom_evidence(None))

    def test_unsafe_duplicate_output_and_existing_files_never_overwritten(self):
        self.output.mkdir()
        witness=self.output/"do-not-touch.txt"
        witness.write_bytes(b"KEEP")
        with self.assertRaises(ValueError):
            stage.stage(self.source,self.output,verify=self.verify,load=self.load)
        self.assertEqual(witness.read_bytes(),b"KEEP")

    def test_symlinked_destination_parent_rejected(self):
        safe=self.root/"safe"
        safe.mkdir()
        link=self.root/"alias"
        link.symlink_to(safe,target_is_directory=True)
        with self.assertRaises(ValueError):
            stage.stage(self.source,link/"new",verify=self.verify,load=self.load)
        self.assertEqual(list(safe.iterdir()),[])

    def test_symlinked_source_and_noncanonical_filename_rejected(self):
        alias=self.root/"alias.zip"
        alias.symlink_to(self.source)
        with self.assertRaises(ValueError):
            stage.stage(alias,self.output,verify=self.verify,load=self.load)
        wrong=self.root/"different.zip"
        wrong.write_bytes(b"mock archive")
        with self.assertRaises(ValueError):
            stage.stage(wrong,self.output,verify=self.verify,load=self.load)
        self.assertFalse(self.output.exists())

    def test_repository_output_rejected_before_rom_verification(self):
        folder=Path(__file__).resolve().parents[1]/"never-export-private-gfx315"
        with self.assertRaises(ValueError):
            stage.stage(self.source,folder,verify=self.verify,load=self.load)
        self.assertFalse(folder.exists())

    def test_non_four_megabyte_gfx_never_staged(self):
        for invalid in (b"test",self.invented[:-1],bytearray(self.invented)):
            with self.subTest(length=len(invalid)):
                with self.assertRaises(ValueError):
                    stage.stage(self.source,self.output,verify=self.verify,
                                load=lambda rom: invalid)
                self.assertFalse(self.output.exists())

    def test_artificial_stage308_bytes_cannot_pass_as_private_original(self):
        fake,_=artificial.build()
        with self.assertRaises(ValueError):
            stage.stage(self.source,self.output,verify=self.verify,
                        load=lambda path:fake)
        self.assertFalse(self.output.exists())

    def test_corrupt_readback_prevents_ready_receipt(self):
        original=stage._readback_matches
        counter=[0]
        def change_on_second(path,data):
            counter[0]+=1
            if counter[0]==2:
                raise ValueError("private fixture readback failure")
            return original(path,data)
        with mock.patch.object(stage,"_readback_matches",
                               side_effect=change_on_second):
            with self.assertRaises(ValueError):
                stage.stage(self.source,self.output,verify=self.verify,
                            load=self.load)
        self.assertFalse((self.output/stage.RECEIPT).exists())

    def test_failed_cli_sanitizes_private_file_path_and_has_no_receipt(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            rc=stage.main(["--rom",str(self.source),
                           "--out-dir",str(self.output)])
        self.assertEqual(rc,2)
        self.assertEqual(out.getvalue().strip(),stage.BLOCKED)
        self.assertNotIn(str(self.root),out.getvalue())
        self.assertFalse(self.output.exists())

    def test_unexpected_unverifiable_graphics_rejected(self):
        with self.assertRaises(ValueError):
            stage.stage(self.source,self.output,verify=self.verify,
                        load=lambda path:None)
        self.assertFalse(self.output.exists())


if __name__=="__main__":
    import unittest
    unittest.main()

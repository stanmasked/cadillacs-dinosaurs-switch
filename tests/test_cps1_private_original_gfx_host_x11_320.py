"""Stage320: synthetic-only public tests, not a NeXium or ROM run."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import cps1_private_original_gfx_host_x11_320 as stage
from tools import nexium_optical_frame_capture_313 as optical


def fabricated_rgba():
    # Invented pixel gradient with many independent sample colors.
    data=bytearray(stage.SCENE_BYTES)
    for y in range(224):
        for x in range(384):
            at=(y*384+x)*4
            data[at:at+4]=bytes((
                (x*31//13)%256,(y*29//11)%256,
                ((x+y)*37//17)%256,255))
    return bytes(data)


class Stage320RealHostOnlyPrivateTestContract(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="stage320-fake-no-rom-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.fake_rom=self.root/"dino.zip"
        self.fake_rom.write_bytes(b"FAKE ONLY, NOT A GAME ROM")
        self.fake_sd=self.root/"sd"
        self.fake_sd.mkdir()
        self.report=self.root/"private-report.json"

    @unittest.skipIf(optical.Image is None,
        "Pillow is optional for baseline Python CI; Stage320 dedicated CI installs it")
    def test_artificial_host_photo_has_25_realistic_control_samples(self):
        reference=fabricated_rgba()
        for index in (0,5,13):
            with self.subTest(index=index):
                frame=stage.compose_host_frame(reference,index)
                self.assertEqual(frame.size,(1280,720))
                optical_id,_,_,_=optical.decode_optical(frame)[0]
                self.assertEqual(optical_id,index)
                self.assertEqual(optical.verify_optical_image(
                    frame,index,reference),25)

    @unittest.skipIf(optical.Image is None,
        "Pillow is optional for baseline Python CI; Stage320 dedicated CI installs it")
    def test_wrong_optical_index_never_passes(self):
        reference=fabricated_rgba()
        frame=stage.compose_host_frame(reference,6)
        with self.assertRaises(ValueError):
            optical.verify_optical_image(frame,7,reference)

    @unittest.skipIf(optical.Image is None,
        "Pillow is optional for baseline Python CI; Stage320 dedicated CI installs it")
    def test_modified_reference_cannot_match_different_host_frame(self):
        original=fabricated_rgba()
        forged=bytes([0])*stage.SCENE_BYTES
        frame=stage.compose_host_frame(original,3)
        with self.assertRaises(ValueError):
            optical.verify_optical_image(frame,3,forged)

    def test_invalid_or_boolean_frame_indices_are_rejected(self):
        example=fabricated_rgba()
        for index in (-1,14,True,1.5,"5"):
            with self.subTest(index=index),self.assertRaises(ValueError):
                stage.compose_host_frame(example,index)

    def test_truncated_or_mutable_scene_bytes_rejected(self):
        example=fabricated_rgba()
        for content in (example[:-1],bytearray(example),None):
            with self.subTest(kind=type(content)),self.assertRaises(ValueError):
                stage.compose_host_frame(content,3)

    def test_report_proves_real_host_only_not_guest_or_gameplay(self):
        with patch.object(stage.original,"_local_inputs",
                          return_value=b"A"*0x400000) as source,patch.object(
                            stage,"_display_all_synthetic_states_with_private_gfx",
                            return_value=(14,25,12)) as host:
            record=stage.run(self.fake_rom,self.fake_sd)
        source.assert_called_once()
        host.assert_called_once()
        self.assertEqual(record["status"],stage.PASS)
        self.assertEqual(record["distinct_reference_frames"],12)
        self.assertEqual(record["minimum_matching_host_optical_sample_points"],25)
        self.assertFalse(record["real_ne_xium_guest_nro_executed"])
        self.assertFalse(record["original_dino_mame_gameplay_executed"])
        self.assertFalse(record["physical_nintendo_switch_execution_verified"])
        self.assertFalse(record["original_rom_derived_graphics_pixels_or_paths_exported"])
        self.assertNotIn(str(self.root),json.dumps(record))

    def test_missing_source_rom_evidence_prevents_any_host_display(self):
        with patch.object(stage.original,"_local_inputs",
                          side_effect=ValueError("fake rom")) as source,patch.object(
                            stage,"_display_all_synthetic_states_with_private_gfx"
                          ) as host:
            with self.assertRaises(ValueError):
                stage.run(self.fake_rom,self.fake_sd)
            host.assert_not_called()

    def test_partial_host_capture_is_not_success(self):
        for partial in ((13,25,12),(14,24,12),(0,0,0)):
            with patch.object(stage.original,"_local_inputs",
                              return_value=b"A"*0x400000),patch.object(
                                stage,"_display_all_synthetic_states_with_private_gfx",
                                return_value=partial):
                with self.subTest(partial=partial),self.assertRaises(ValueError):
                    stage.run(self.fake_rom,self.fake_sd)

    def test_cli_failure_sanitizes_real_path_and_writes_private_receipt(self):
        stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc=stage.main(["--rom",str(self.fake_rom),
                           "--sd-root",str(self.fake_sd),
                           "--out",str(self.report)])
        self.assertEqual(rc,2)
        self.assertEqual(stdout.getvalue().strip(),stage.BLOCKED)
        report=json.loads(self.report.read_text())
        self.assertEqual(self.report.stat().st_mode&0o777,0o600)
        self.assertNotIn(str(self.root),json.dumps(report))
        self.assertFalse(report["host_pixels_read_by_real_x11_getimage"])

    def test_public_repository_output_refused_without_writing(self):
        output=Path(__file__).resolve().parents[1]/"never-output-original-gfx320.json"
        with contextlib.redirect_stdout(io.StringIO()):
            rc=stage.main(["--rom",str(self.fake_rom),
                           "--sd-root",str(self.fake_sd),"--out",str(output)])
        self.assertEqual(rc,2)
        self.assertFalse(output.exists())

    def test_existing_private_output_never_overwritten(self):
        self.report.write_text("KEEP ORIGINAL")
        with contextlib.redirect_stdout(io.StringIO()):
            rc=stage.main(["--rom",str(self.fake_rom),
                           "--sd-root",str(self.fake_sd),"--out",str(self.report)])
        self.assertEqual(rc,2)
        self.assertEqual(self.report.read_text(),"KEEP ORIGINAL")

    def test_source_requires_actual_x11_getimage_not_pil_mock(self):
        source=(Path(__file__).resolve().parents[1]/
                "tools/cps1_private_original_gfx_host_x11_320.py").read_text()
        self.assertIn("window.get_image(0,0,geom.width,geom.height",source)
        self.assertIn("optical.verify_optical_image(",source)
        self.assertIn("original._local_inputs(",source)
        self.assertIn("real_ne_xium_guest_nro_executed\":False",source)


if __name__=="__main__":
    unittest.main()

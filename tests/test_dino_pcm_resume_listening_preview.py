"""Actual-GCC ROM-free WAV render tests; not Switch speaker measurements."""
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest import mock
import wave

from tools import dino_pcm_resume_listening_preview as preview


@unittest.skipUnless(shutil.which("gcc"),"native GCC required for real C audio")
class SynthesizedPCMListeningPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="dino-wav-fixture-")
        cls.root=Path(cls.temp.name)
        cls.report=preview.generate(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def setUpClass_no_extra_artifacts(cls):
        pass

    def load(self,name):
        with wave.open(str(self.root/name),"rb") as wav:
            self.assertEqual(wav.getnchannels(),2)
            self.assertEqual(wav.getsampwidth(),2)
            self.assertEqual(wav.getframerate(),48000)
            self.assertEqual(wav.getnframes(),preview.TOTAL)
            raw=wav.readframes(preview.TOTAL)
            self.assertEqual(wav.readframes(1),b"")
        data=struct.unpack("<"+str(len(raw)//2)+"h",raw)
        return list(data)

    def test_three_real_pcm_wav_outputs_and_manifest(self):
        self.assertEqual(set(self.report["files"][i]["file_name"]
                             for i in range(3)),set(preview.FILE_NAMES))
        self.assertEqual(self.report["status"],
            "SYNTHETIC_WAV_C_FIXED_VS_GUARDED_PCM_ATTACK")
        self.assertTrue(self.report["no_original_game_assets_included"])
        self.assertFalse(self.report["audible_click_reduction_proven"])
        self.assertFalse(self.report["physical_switch_speaker_verified"])
        self.assertFalse(self.report["production_enablement_recommended"])
        manifest=json.loads((self.root/"listening-preview-manifest.json").read_text())
        self.assertEqual(manifest,self.report)
        for track in preview.FILE_NAMES:
            self.assertEqual(len(self.load(track)),preview.TOTAL*2)

    def test_guard_allows_silence_resumption_and_rejects_continuous_audio(self):
        a,b=self.report["episodes"]
        self.assertEqual(a["name"],"silence_to_tone")
        self.assertEqual(b["name"],"continuous_tone")
        self.assertTrue(a["guarded_proxy_selected"])
        self.assertFalse(b["guarded_proxy_selected"])
        self.assertGreater(a["raw_boundary_steps"][0],
                           a["fixed_ramp_boundary_steps"][0])
        self.assertEqual(a["fixed_ramp_boundary_steps"],
                         a["guarded_proxy_boundary_steps"])
        self.assertGreater(b["fixed_ramp_boundary_steps"][0],
                           b["raw_boundary_steps"][0])
        self.assertEqual(b["guarded_proxy_boundary_steps"],
                         b["raw_boundary_steps"])

    def test_exact_region_isolation_no_missing_samples_or_phase_shift(self):
        raw=self.load("raw.wav")
        fixed=self.load("fixed_ramp.wav")
        guarded=self.load("guarded_proxy.wav")
        first=2*preview.A_POS
        second=2*preview.B_POS
        duration=2*preview.ATTACK_FRAMES
        self.assertEqual(raw[:first],fixed[:first])
        self.assertEqual(raw[:first],guarded[:first])
        self.assertEqual(raw[first+duration:second],
                         fixed[first+duration:second])
        self.assertEqual(raw[first+duration:second],
                         guarded[first+duration:second])
        self.assertEqual(raw[second+duration:],
                         fixed[second+duration:])
        self.assertEqual(raw[second:],guarded[second:])
        self.assertNotEqual(raw[first:first+duration],
                            fixed[first:first+duration])
        self.assertEqual(fixed[first:first+duration],
                         guarded[first:first+duration])
        self.assertNotEqual(raw[second:second+duration],
                            fixed[second:second+duration])

    def test_wav_hashes_reproduce_manifest_and_are_distinct(self):
        import hashlib
        observed=[]
        for item in self.report["files"]:
            data=self.load(item["file_name"])
            pcm=preview.pcm_bytes(data)
            self.assertEqual(hashlib.sha256(pcm).hexdigest(),
                             item["sha256_pcm_le"])
            self.assertEqual(len(pcm),item["pcm_bytes"])
            observed.append(item["sha256_pcm_le"])
        self.assertEqual(len(set(observed)),3)

    def test_exclusive_no_overwrite_preserves_previous_wavs_and_json(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        with self.assertRaisesRegex(ValueError,"overwrite"):
            preview.generate(self.root)
        after={p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before,after)

    def test_tone_uses_only_bounded_invented_stereo_samples(self):
        self.assertEqual(len(preview.tone(800)),1600)
        self.assertEqual(preview.tone(0),[])
        for s in preview.tone(1000):
            self.assertTrue(-32768<=s<=32767)
        for bad in (-1,preview.RATE*11,False,None,3.5):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                preview.tone(bad)

    def test_main_with_no_native_compiler_fails_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            with mock.patch.object(preview.shutil,"which",return_value=None):
                with self.assertRaises(ValueError):
                    preview.generate(path)
            self.assertEqual(list(path.iterdir()),[])

    def test_reject_nonexistent_output_path_before_native_build(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"unknown"
            with self.assertRaisesRegex(ValueError,"empty real destination"):
                preview.generate(path)
            self.assertFalse(path.exists())

    def test_current_signal_is_not_commercial_audio_or_guest_capture(self):
        source=(preview.ROOT/"tools"/
                "dino_pcm_resume_listening_preview.py").read_text()
        self.assertIn("newly_invented_440hz_cosine_not_game_audio",source)
        self.assertIn("not its last *played* sample",source)
        self.assertNotIn("audoutGetReleased",source)
        self.assertNotIn("dino.zip",source)
        self.assertEqual(preview.RATE,48000)
        self.assertEqual(preview.ATTACK_FRAMES,96)


if __name__=="__main__":
    unittest.main()

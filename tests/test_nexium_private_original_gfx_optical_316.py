"""Stage316 public regressions: NO original ROM, only invented byte fixtures."""
import contextlib
import io
import json
import signal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

from tools import nexium_private_original_gfx_optical_316 as stage
from tools import cps1_synthetic_scene_sequence_307 as invented
from tools import cps1_private_original_gfx_synthetic_sd_315 as sdstage
from tools import verify_nexium_synthetic_scene_guest_312 as guest


class Stage316PrivateOpticalSafety(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="stage316-no-real-rom-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.rom=self.root/"dino.zip"
        self.rom.write_bytes(b"NOT A ROM: MOCK ONLY")
        self.sd=self.root/"private-sd"
        self.app=self.sd/"switch"/"cadillacs-dinosaurs-switch"
        self.app.mkdir(parents=True)
        self.gfx=bytes(range(256))*(stage.GFX_BYTES//256)
        from tools import cps1_synthetic_scene_sequence_307 as timeline
        scene,_=timeline.build(fps=2)
        (self.app/"gfx.bin").write_bytes(self.gfx)
        (self.app/"sequence.bin").write_bytes(scene)
        for file in self.app.iterdir():file.chmod(0o600)
        self.trace=self.sd/"cadillacs-synthetic-scene-guest.csv"

    @staticmethod
    def mock_verified():
        from tools import mame0106_private_dino_rom_canonicalize_299 as canon
        return {
            "status":canon.MATCH,
            "required_rom_members_matched_by_crc32_sha1":16,
            "required_payloads_crc_sha1_integrity_checked":True,
            "all_original_payload_bytes_kept_private":True,
        }

    def test_private_source_gate_and_exact_sd_readback(self):
        got=stage._local_inputs(self.rom,self.sd,
            verify=lambda rom,manifest:self.mock_verified(),
            read_gfx=lambda rom:self.gfx)
        self.assertEqual(got,self.gfx)

    def test_rom_verification_precedes_reading_original_gfx(self):
        calls=[]
        with self.assertRaises(ValueError):
            stage._local_inputs(self.rom,self.sd,
                verify=lambda rom,manifest:{"status":"BLOCKED"},
                read_gfx=lambda rom:calls.append(rom))
        self.assertEqual(calls,[])

    def test_incomplete_original_rom_evidence_refused(self):
        for key,bad in (
            ("required_rom_members_matched_by_crc32_sha1",True),
            ("required_rom_members_matched_by_crc32_sha1",15),
            ("required_payloads_crc_sha1_integrity_checked",False),
            ("all_original_payload_bytes_kept_private",False),
        ):
            evidence=self.mock_verified(); evidence[key]=bad
            with self.subTest(field=key),self.assertRaises(ValueError):
                stage._local_inputs(self.rom,self.sd,
                    verify=lambda rom,manifest:evidence,
                    read_gfx=lambda rom:self.gfx)

    def test_original_graphics_must_match_actual_private_sd_bytes(self):
        bad=bytearray(self.gfx);bad[-1]^=1
        (self.app/"gfx.bin").write_bytes(bad)
        with self.assertRaises(ValueError):
            stage._local_inputs(self.rom,self.sd,
                verify=lambda rom,manifest:self.mock_verified(),
                read_gfx=lambda rom:self.gfx)

    def test_artificial_gfx_marker_refused_even_with_mocked_crc(self):
        from tools import cps1_synthetic_gfx_fixture_308 as artificial
        fake,_=artificial.build()
        with self.assertRaises(ValueError):
            stage._local_inputs(self.rom,self.sd,
                verify=lambda rom,manifest:self.mock_verified(),
                read_gfx=lambda rom:fake)

    def test_modified_sequence_refused_even_after_valid_outer_crc(self):
        timeline,_=invented.build(fps=2)
        mutated=bytearray(timeline);mutated[-3]^=1
        (self.app/"sequence.bin").write_bytes(mutated)
        with self.assertRaises(ValueError):
            stage._local_inputs(self.rom,self.sd,
                verify=lambda rom,manifest:self.mock_verified(),
                read_gfx=lambda rom:self.gfx)

    def test_malformed_private_gfx_permissions_or_symlink_refused(self):
        target=self.app/"gfx.bin"
        target.chmod(0o644)
        with self.assertRaises(ValueError):
            stage._local_inputs(self.rom,self.sd,
                verify=lambda rom,manifest:self.mock_verified(),
                read_gfx=lambda rom:self.gfx)
        target.chmod(0o600)
        target.unlink()
        real=self.root/"outside.bin";real.write_bytes(self.gfx)
        target.symlink_to(real)
        with self.assertRaises(ValueError):
            stage._local_inputs(self.rom,self.sd,
                verify=lambda rom,manifest:self.mock_verified(),
                read_gfx=lambda rom:self.gfx)

    def test_native_scene_hash_must_match_reference_before_host_ack(self):
        reference=b"PRIVATE-MOCK-RGBA"
        crc=guest.fnv64(reference)
        self.trace.write_text(guest.HEADER+
            "\nFRAME_SUBMITTED,0,%016X,%016X\n"%(crc,0x22131448))
        self.assertTrue(stage._check_guest_row(self.trace,0,reference))
        with self.assertRaises(ValueError):
            stage._check_guest_row(self.trace,0,reference+b"X")
        self.assertFalse(stage._check_guest_row(self.trace,1,reference))

    def test_original_scene_trace_requires_fourteen_unique_samples(self):
        references=[guest.fnv64(str(i).encode()) for i in range(14)]
        def text_for(samples):
            return (guest.HEADER+"\n"+"\n".join(
                "FRAME_SUBMITTED,%d,%016X,%016X"%(i,references[i],v)
                for i,v in enumerate(samples))+"\n")
        self.trace.write_text(text_for([3+i for i in range(14)]))
        self.assertEqual(stage._check_final_trace(self.trace,references),14)
        self.trace.write_text(text_for([10]*14))
        with self.assertRaises(ValueError):
            stage._check_final_trace(self.trace,references)
        self.trace.write_text(text_for([3+i for i in range(13)]))
        with self.assertRaises(ValueError):
            stage._check_final_trace(self.trace,references)

    def test_guest_trace_cannot_be_reused_at_start_of_another_run(self):
        self.trace.write_text(guest.HEADER+"\n")
        # This is a host-only check. No emulator or real NRO started.
        with self.assertRaises(ValueError):
            stage._run(Path("/nothing"),Path("/nothing"),self.sd,
                       self.root,self.gfx,0.0)

    def test_direct_launch_is_unchanged_when_no_isolated_runtime_requested(self):
        exe=self.root/"nexium";nro=self.root/"game.nro"
        self.assertEqual(stage._launch_argv(exe,nro,{}),[str(exe),str(nro)])

    def test_isolated_launch_uses_pinned_loader_and_explicit_library_path(self):
        sysroot=self.root/"glibc"/"lib"/"x86_64-linux-gnu"
        sysroot.mkdir(parents=True)
        loader=sysroot/"ld-linux-x86-64.so.2"
        loader.write_text("#!/bin/sh\\nexit 0\\n")
        loader.chmod(0o700)
        for soname in ("libc.so.6","libm.so.6"):
            (sysroot/soname).write_bytes(b"PUBLIC-MOCK-GLIBC-LIBRARY")
        system=self.root/"system-libs";system.mkdir()
        library_path=str(sysroot)+":"+str(system)
        argv=stage._launch_argv(self.root/"nexium",self.root/"game.nro",{
            "NEXIUM_DYNAMIC_LOADER":str(loader),
            "NEXIUM_ISOLATED_LIBRARY_PATH":library_path,
        })
        self.assertEqual(argv,[
            str(loader),"--inhibit-cache","--library-path",library_path,
            str(self.root/"nexium"),str(self.root/"game.nro")])

    def test_isolated_linkage_must_resolve_libc_and_libm_inside_sysroot(self):
        sysroot=self.root/"glibc"/"lib"
        sysroot.mkdir(parents=True)
        loader=sysroot/"ld-linux-x86-64.so.2"
        loader.write_text("#!/bin/sh\\nexit 0\\n");loader.chmod(0o700)
        for soname in ("libc.so.6","libm.so.6"):
            (sysroot/soname).write_bytes(b"MOCK-ONLY")
        system=self.root/"system-libs";system.mkdir()
        library_path=str(sysroot)+":"+str(system)
        exe=self.root/"nexium"
        command=stage._launch_argv(exe,self.root/"game.nro",{
            "NEXIUM_DYNAMIC_LOADER":str(loader),
            "NEXIUM_ISOLATED_LIBRARY_PATH":library_path})
        good=("libc.so.6 => "+str(sysroot/"libc.so.6")+" (0x1)\\n"+
              "libm.so.6 => "+str(sysroot/"libm.so.6")+" (0x2)\\n").encode()
        with patch.object(stage.subprocess,"run",return_value=type(
                "Result",(),{"returncode":0,"stdout":good})()):
            stage._verify_isolated_linkage(exe,command)
        bad=("libc.so.6 => "+str(sysroot/"libc.so.6")+" (0x1)\\n"+
             "libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x2)\\n").encode()
        with patch.object(stage.subprocess,"run",return_value=type(
                "Result",(),{"returncode":0,"stdout":bad})()):
            with self.assertRaises(ValueError):
                stage._verify_isolated_linkage(exe,command)

    def test_isolated_launch_refuses_partial_or_incomplete_sysroot(self):
        with self.assertRaises(ValueError):
            stage._launch_argv(self.root/"nexium",self.root/"game.nro",{
                "NEXIUM_DYNAMIC_LOADER":"/tmp/loader-only"})
        sysroot=self.root/"glibc"/"lib"
        sysroot.mkdir(parents=True)
        loader=sysroot/"ld-linux-x86-64.so.2"
        loader.write_text("#!/bin/sh\\nexit 0\\n");loader.chmod(0o700)
        (sysroot/"libc.so.6").write_bytes(b"MOCK-ONLY")
        system=self.root/"system-libs";system.mkdir()
        with self.assertRaises(ValueError):
            stage._launch_argv(self.root/"nexium",self.root/"game.nro",{
                "NEXIUM_DYNAMIC_LOADER":str(loader),
                "NEXIUM_ISOLATED_LIBRARY_PATH":str(sysroot)+":"+str(system)})

    def test_isolated_launch_refuses_symlinked_loader(self):
        sysroot=self.root/"glibc"/"lib"
        sysroot.mkdir(parents=True)
        real=self.root/"real-loader"
        real.write_text("#!/bin/sh\\nexit 0\\n");real.chmod(0o700)
        alias=sysroot/"ld-linux-x86-64.so.2";alias.symlink_to(real)
        (sysroot/"libc.so.6").write_bytes(b"MOCK-ONLY")
        (sysroot/"libm.so.6").write_bytes(b"MOCK-ONLY")
        system=self.root/"system-libs";system.mkdir()
        with self.assertRaises(ValueError):
            stage._launch_argv(self.root/"nexium",self.root/"game.nro",{
                "NEXIUM_DYNAMIC_LOADER":str(alias),
                "NEXIUM_ISOLATED_LIBRARY_PATH":str(sysroot)+":"+str(system)})

    def test_cleanup_signals_the_whole_ne_xium_process_group(self):
        # The leader may already have exited while a GUI/helper child remains.
        class Proc:
            pid = 43122
            def wait(self, timeout=None): return 0
            def poll(self): return 0
        with patch.object(stage.os, "killpg") as killpg:
            stage._terminate_process_group(Proc())
        self.assertEqual(killpg.call_args_list,[
            call(43122,signal.SIGTERM),call(43122,signal.SIGKILL)])

    def test_cleanup_escalates_when_process_leader_ignores_term(self):
        class Proc:
            pid = 43123
            def __init__(self): self.alive=True
            def wait(self, timeout=None):
                if self.alive and timeout==6:
                    from subprocess import TimeoutExpired
                    raise TimeoutExpired("ne-xium",timeout)
                self.alive=False
                return 0
            def poll(self): return None if self.alive else 0
        proc=Proc()
        def fake_killpg(pgid, sig):
            if sig==signal.SIGKILL: proc.alive=False
        with patch.object(stage.os,"killpg",side_effect=fake_killpg) as killpg:
            stage._terminate_process_group(proc)
        self.assertEqual(killpg.call_args_list,[
            call(43123,signal.SIGTERM),call(43123,signal.SIGKILL)])
        self.assertEqual(proc.poll(),0)

    def test_source_level_optin_flag_and_no_stage308_alias(self):
        # Compile macro guards prevent accidental physical game's origin
        # confusion. The actual NRO compile job checks this too.
        code=(Path(__file__).resolve().parents[1]/"source/main.c").read_text()
        self.assertIn("#ifdef DINO_PRIVATE_ORIGINAL_GFX_HOST_VISIBLE_316",code)
        self.assertIn("const bool private_scene_guest_ready =",code)
        self.assertIn('memcmp(gfx,"ROM-FREE CPS1 SYNTHETIC PIXELS STAGE308",39u)!=0',code)
        self.assertIn("const bool optical_guest_ready = private_scene_guest_ready;",code)

    def test_fail_closed_cli_writes_only_private_redacted_receipt(self):
        report=self.root/"failed-receipt.json"
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            code=stage.main([
                "--exe",str(self.root/"missing-emulator"),
                "--nro",str(self.root/"missing.nro"),
                "--rom",str(self.rom),
                "--sd-root",str(self.sd),
                "--summary",str(report)])
        self.assertEqual(code,2)
        self.assertEqual(out.getvalue().strip(),stage.BLOCKED)
        receipt=json.loads(report.read_text())
        self.assertNotIn(str(self.root),json.dumps(receipt))
        self.assertFalse(receipt["original_graphics_uploaded_to_public_github"])
        self.assertFalse(receipt["all_host_visible_scene_ids_and_pixels_match_python"])
        self.assertEqual(report.stat().st_mode & 0o777,0o600)


if __name__=="__main__":
    unittest.main()

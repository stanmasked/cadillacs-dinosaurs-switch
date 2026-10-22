#!/usr/bin/env python3
"""Stage316: PRIVATE source-verified original gfx + synthetic scene optical proof.

An authentic NeXium host-window proof must come from actual guest trace rows
AND real X11 pixels for every scene. The canonical 16-member original ROM is
verified locally, not uploaded. This is NOT original game execution: scene
state, palettes, objects and priorities are deliberately invented.

Requires an opt-in Stage316 Switch NRO compiled from source/main.c, a
PRIVATE Stage315 SD staging root, and a locally pinned NeXium executable.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

try:
    from . import mame0106_private_dino_rom_canonicalize_299 as canonical
    from . import cps1_private_native_tile_parity as original
    from . import cps1_synthetic_scene_sequence_307 as invented
    from . import cps1_private_scene_compositor_parity as scenes
    from . import cps1_frame
    from . import verify_nexium_synthetic_scene_guest_312 as guest
    from . import nexium_optical_frame_capture_313 as optical
    from . import nexium_x11_process_window_319 as x11
    from . import wolfmame0106_private_binary_gate as guard
except ImportError:
    import mame0106_private_dino_rom_canonicalize_299 as canonical
    import cps1_private_native_tile_parity as original
    import cps1_synthetic_scene_sequence_307 as invented
    import cps1_private_scene_compositor_parity as scenes
    import cps1_frame
    import verify_nexium_synthetic_scene_guest_312 as guest
    import nexium_optical_frame_capture_313 as optical
    import nexium_x11_process_window_319 as x11
    import wolfmame0106_private_binary_gate as guard

SCHEMA = "dino-stage316-private-original-gfx-synthetic-ne-xium-optical-v1"
PASS = "PRIVATE_ORIGINAL_CPS1_GFX_SYNTHETIC_SCENES_14_HOST_X11_MATCH"
BLOCKED = "BLOCKED_PRIVATE_ORIGINAL_GFX_NE_XIUM_X11_PROOF"
COUNT = 14
GFX_BYTES = 0x400000


def _local_inputs(rom, sd_root, *, verify=None, read_gfx=None):
    """Fail closed before starting an emulated game, or creating a receipt."""
    rom = canonical._private_regular(Path(rom),canonical.MAX_ZIP_BYTES)
    if rom.name != "dino.zip":
        raise ValueError("source archive must be a private canonical dino.zip")
    if verify is None: verify=canonical.verify_archive
    if read_gfx is None: read_gfx=original.read_private_gfx
    receipt=verify(rom,manifest=canonical.MANIFEST)
    if (type(receipt) is not dict or receipt.get("status")!=canonical.MATCH
        or type(receipt.get("required_rom_members_matched_by_crc32_sha1")) is not int
        or receipt["required_rom_members_matched_by_crc32_sha1"]!=len(canonical.MANIFEST)
        or receipt.get("required_payloads_crc_sha1_integrity_checked") is not True
        or receipt.get("all_original_payload_bytes_kept_private") is not True):
        raise ValueError("sixteen original ROM source hash identities not verified")
    expected_gfx=read_gfx(rom)
    if (type(expected_gfx) is not bytes or len(expected_gfx)!=GFX_BYTES
        or expected_gfx.startswith(b"ROM-FREE CPS1 SYNTHETIC PIXELS STAGE308")):
        raise ValueError("not a source-recovered original graphics region")
    sd_root=Path(sd_root)
    if (not guard.outside_repo(sd_root) or sd_root.is_symlink()
        or not sd_root.is_dir()
        or any(p.is_symlink() for p in sd_root.parents)):
        raise ValueError("unsafe private SD root")
    base=sd_root/"switch"/"cadillacs-dinosaurs-switch"
    graphics=base/"gfx.bin"
    seqfile=base/"sequence.bin"
    for file in (graphics,seqfile):
        if (file.is_symlink() or not file.is_file()
            or (file.stat().st_mode & 0o777)!=0o600):
            raise ValueError("unsafe input file in private SD root")
    if graphics.stat().st_size!=GFX_BYTES or graphics.read_bytes()!=expected_gfx:
        raise ValueError("private SD graphics do not exactly match original ROM")
    sequence_bytes, proof=invented.build(fps=2)
    if (proof["status"]!=invented.PASS
        or proof["frame_states_are_synthetic"] is not True
        or seqfile.stat().st_size!=len(sequence_bytes)
        or seqfile.read_bytes()!=sequence_bytes):
        raise ValueError("private SD synthetic scene state is not canonical")
    return expected_gfx


def _check_guest_row(trace, index, reference):
    """Actual guest FRAME_SUBMITTED row matches the independent Python frame."""
    if not optical._complete_rows(trace,index):
        return False
    rows=trace.read_text(encoding="ascii").splitlines()
    match=guest.LINE.fullmatch(rows[index+1])
    if not match or int(match.group(1))!=index:
        raise ValueError("missing or out of order native guest scene")
    if int(match.group(2),16)!=guest.fnv64(reference):
        raise ValueError("native original graphics scene differs from Python")
    if int(match.group(3),16)==0:
        raise ValueError("native guest framebuffer sample empty")
    return True


def _check_final_trace(trace, reference_hashes):
    if trace.is_symlink() or not trace.is_file() or trace.stat().st_size>2048:
        raise ValueError("missing bounded private native guest trace")
    rows=trace.read_text(encoding="ascii").splitlines()
    if len(rows)!=COUNT+1 or rows[0]!=guest.HEADER:
        raise ValueError("incomplete private native guest trace")
    samples=set()
    for index in range(COUNT):
        match=guest.LINE.fullmatch(rows[index+1])
        if not match or int(match.group(1))!=index:
            raise ValueError("invalid private native guest row ordering")
        if int(match.group(2),16)!=reference_hashes[index]:
            raise ValueError("native original GFX scene hash mismatch")
        screen=int(match.group(3),16)
        if not screen: raise ValueError("empty native scene framebuffer sample")
        samples.add(screen)
    if len(samples)<4 or len(set(reference_hashes))<4:
        raise ValueError("private original scene pixels insufficiently varied")
    return len(samples)


def _run(exe,nro,sd_root,root,gfx,deadline):
    trace=sd_root/"cadillacs-synthetic-scene-guest.csv"
    if trace.exists() or trace.is_symlink():
        raise ValueError("refuse a stale guest trace from earlier emulation")
    for i in range(COUNT):
        if (sd_root/("cadillacs-synthetic-scene-next-%02d.txt"%i)).exists():
            raise ValueError("refuse stale previous private X11 acknowledgments")
    refs=[]
    for case in scenes.CASES:
        snap=scenes.synthetic_scene(case)
        frame=cps1_frame.render_frame(
            gfx,[tuple(entry) for entry in snap["palette_rgb"]],snap)
        refs.append(frame)
    scores=[]
    with open(root/"private-ne-xium-console.txt","wb") as console:
        with subprocess.Popen([str(exe),str(nro)],stdout=console,
                              stderr=subprocess.STDOUT) as proc:
            try:
                for index,reference in enumerate(refs):
                    while not _check_guest_row(trace,index,reference):
                        if proc.poll() is not None or time.monotonic()>deadline:
                            raise ValueError("guest ROM graphics frame not submitted")
                        time.sleep(.15)
                    matched=0
                    while matched<10:
                        if proc.poll() is not None or time.monotonic()>deadline:
                            raise ValueError("real private host X11 pixels missing")
                        wid=x11.window_for_process(proc.pid)
                        if wid:
                            try:
                                host=optical._capture(wid,root/"host-window.png")
                                matched=optical.verify_optical_image(host,index,reference)
                            except (ValueError,OSError,subprocess.SubprocessError):
                                matched=0
                        if matched<10: time.sleep(.18)
                    scores.append(matched)
                    if index<COUNT-1:
                        ack=sd_root/("cadillacs-synthetic-scene-next-%02d.txt"%index)
                        with ack.open("x",encoding="ascii") as handle:
                            handle.write("NEXT,%d\n"%index)
                            handle.flush()
                            os.fsync(handle.fileno())
                unique=_check_final_trace(trace,[guest.fnv64(x) for x in refs])
                return {
                    "schema":SCHEMA,
                    "status":PASS,
                    "original_source_rom_members_crc_sha1_checked":16,
                    "private_original_cps1_graphics_bytes":GFX_BYTES,
                    "synthetic_scene_states_used":True,
                    "guest_submitted_original_graphics_synthetic_frames":COUNT,
                    "host_x11_optical_original_graphics_synthetic_frames":COUNT,
                    "host_scene_reference_min_matched_pixels":min(scores),
                    "unique_native_framebuffer_samples":unique,
                    "all_guest_original_graphics_scene_hashes_match_python":True,
                    "all_host_visible_scene_ids_and_pixels_match_python":True,
                    "actual_original_game_executed":False,
                    "actual_original_game_vram_palette_observed":False,
                    "original_inp_wlf_replay_verified":False,
                    "physical_nintendo_switch_display_verified":False,
                    "private_original_pixels_paths_or_hashes_exported":False,
                    "original_graphics_uploaded_to_public_github":False,
                }
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try: proc.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=6)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ("exe","nro","rom","sd-root","summary"):
        parser.add_argument("--"+arg,required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        destination=args.summary
        if (not guard.outside_repo(destination) or
            destination.exists() or destination.is_symlink() or
            destination.parent.is_symlink() or
            not destination.parent.is_dir()):
            raise ValueError("output must be a new private outside-repo file")
        gfx=_local_inputs(args.rom,args.sd_root)
        if not args.exe.is_file() or not args.nro.is_file():
            raise ValueError("no actual NeXium executable / Switch NRO provided")
        with tempfile.TemporaryDirectory(prefix="private-gfx-ne-xium-316-") as d:
            summary=_run(args.exe.resolve(),args.nro.resolve(),
                         args.sd_root.resolve(),Path(d),gfx,
                         time.monotonic()+160)
        code=0
    except Exception:
        # No exception text or raw guest framebuffer bytes leave local host.
        summary={
            "schema":SCHEMA,"status":BLOCKED,
            "all_host_visible_scene_ids_and_pixels_match_python":False,
            "actual_original_game_executed":False,
            "physical_nintendo_switch_display_verified":False,
            "private_original_pixels_paths_or_hashes_exported":False,
            "original_graphics_uploaded_to_public_github":False,
        }
        code=2
    guard.write_private_receipt(args.summary,summary)
    print(summary["status"])
    return code


if __name__=="__main__":
    raise SystemExit(main())

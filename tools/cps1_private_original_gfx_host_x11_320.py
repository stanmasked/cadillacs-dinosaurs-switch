#!/usr/bin/env python3
"""Stage320: real X11 HOST-only optical display of private ORIGINAL CPS-1 GFX.

The user's source-verified 16-member original MAME 0.106 ROM is strictly
private. All scene state (tilemaps, sprites, palette, priority) is invented
Stage307/305 data. This test displays 14 Python-rendered RGBA frames in a
REAL X11 Tk window, reads actual X server pixels back via python-xlib,
and compares all 25 sampled scene pixels plus optical frame ID.

NO NeXium process, guest Nintendo Switch NRO, authentic original MAME
runtime frame, or real game VRAM is involved. Never claim any of these.
Never write decoded graphics/screenshots, raw frames or source digests.
"""
import argparse
import hashlib
import os
from pathlib import Path

try:
    from . import nexium_private_original_gfx_optical_316 as original
    from . import cps1_private_scene_compositor_parity as scenes
    from . import cps1_frame
    from . import nexium_optical_frame_capture_313 as optical
    from . import wolfmame0106_private_binary_gate as guard
except ImportError:
    import nexium_private_original_gfx_optical_316 as original
    import cps1_private_scene_compositor_parity as scenes
    import cps1_frame
    import nexium_optical_frame_capture_313 as optical
    import wolfmame0106_private_binary_gate as guard

SCHEMA = "dino-stage320-private-original-gfx-real-host-x11-not-ne-xium-v1"
PASS = "PRIVATE_ORIGINAL_GFX_REAL_HOST_X11_14_OF_14_OPTICAL_CONFIRMED_NOT_NE_XIUM"
BLOCKED = "BLOCKED_PRIVATE_ORIGINAL_GFX_HOST_X11_OPTICAL"
SCENE_BYTES = 384*224*4
COUNT = 14
FRAME_W = 1280
FRAME_H = 720
MIN_REQUIRED_MATCHING_SAMPLES = len(optical.POINTS)


def compose_host_frame(reference, index, *, Image=None, ImageDraw=None):
    """Produce the exact public Stage313 optical layout from an RGBA scene.

    No host capture or guest evidence is produced by this helper alone.
    """
    if (type(reference) is not bytes or len(reference)!=SCENE_BYTES
            or type(index) is not int or not 0<=index<COUNT):
        raise ValueError("invalid original/synthetic scene reference")
    if Image is None or ImageDraw is None:
        from PIL import Image as ImageModule, ImageDraw as DrawModule
        Image=ImageModule
        ImageDraw=DrawModule
    source=Image.frombytes("RGBA",(384,224),reference).convert("RGB")
    full=Image.new("RGB",(FRAME_W,FRAME_H),(25,25,25))
    full.paste(source.resize((1152,672),Image.Resampling.NEAREST),(64,24))
    drawer=ImageDraw.Draw(full)
    for x in (8,1250):
        drawer.rectangle((x,188,x+17,205),fill=(255,0,255))
    for bit in range(4):
        y=214+bit*26
        drawer.rectangle((8,y,25,y+17),fill=(
            (0,255,0) if index&(1<<bit) else (255,0,0)))
    return full


def _read_real_x11_window(window_id, display, image_module):
    """Read REAL X server pixels, never a copy of the input PIL buffer."""
    from Xlib import X
    if type(window_id) is not int or window_id<=0:
        raise ValueError("invalid live X11 window id")
    window=display.create_resource_object("window",window_id)
    geom=window.get_geometry()
    if geom.width!=FRAME_W or geom.height!=FRAME_H:
        raise ValueError("unexpected host X11 window geometry")
    snapshot=window.get_image(0,0,geom.width,geom.height,
                              X.ZPixmap,0xffffffff)
    if (snapshot.depth!=24 or
            len(snapshot.data)!=FRAME_W*FRAME_H*4):
        raise ValueError("this host needs little-endian 24-bit Xvfb BGRX")
    return image_module.frombytes("RGB",(FRAME_W,FRAME_H),
                                  snapshot.data,"raw","BGRX")


def _display_all_synthetic_states_with_private_gfx(gfx):
    """Only local private host display; no ROM file or pixels persisted."""
    if (type(gfx) is not bytes or len(gfx)!=0x400000 or
            os.environ.get("DISPLAY","")=="" or
            len(scenes.CASES)!=COUNT):
        raise ValueError("original graphics or X11 display unavailable")
    import tkinter as tk
    from PIL import Image, ImageDraw, ImageTk
    from Xlib import display as xdisplay
    root=None
    server=None
    samples=[]
    distinct=set()
    try:
        root=tk.Tk()
        root.title("Private Stage320 CPS-1 X11 host-only optical check")
        root.overrideredirect(True)
        root.geometry("1280x720+0+0")
        label=tk.Label(root,borderwidth=0,highlightthickness=0)
        label.pack()
        root.update()
        server=xdisplay.Display()
        win_id=root.winfo_id()
        for index,case in enumerate(scenes.CASES):
            state=scenes.synthetic_scene(case)
            reference=cps1_frame.render_frame(
                gfx,[tuple(entry) for entry in state["palette_rgb"]],
                state)
            if type(reference) is not bytes or len(reference)!=SCENE_BYTES:
                raise ValueError("independent original graphics reference invalid")
            distinct.add(hashlib.sha256(reference).digest())
            picture=compose_host_frame(reference,index,
                                       Image=Image,ImageDraw=ImageDraw)
            photo=ImageTk.PhotoImage(picture)
            label.configure(image=photo)
            label.image=photo
            root.update()
            # The source PIL picture is NOT treated as host evidence. The
            # X server must respond to a genuine GetImage from this window.
            observed=_read_real_x11_window(win_id,server,Image)
            matched=optical.verify_optical_image(
                observed,index,reference)
            if matched!=MIN_REQUIRED_MATCHING_SAMPLES:
                raise ValueError("not all 25 private X11 scene points match")
            samples.append(matched)
    finally:
        if server is not None:
            server.close()
        if root is not None:
            root.destroy()
    if len(samples)!=COUNT or len(distinct)<4:
        raise ValueError("too few independent host-visible scene states")
    return len(samples),min(samples),len(distinct)


def run(rom,sd_root):
    """The Stage316 private gate authenticates ROM and exact SD bytes first."""
    gfx=original._local_inputs(Path(rom),Path(sd_root))
    count,smallest,distinct=_display_all_synthetic_states_with_private_gfx(gfx)
    if count!=COUNT or smallest!=MIN_REQUIRED_MATCHING_SAMPLES:
        raise ValueError("host X11 optical images incomplete")
    return {
        "schema": SCHEMA,
        "status": PASS,
        "original_rom_members_source_crc_sha1_verified":16,
        "private_original_cps1_graphics_bytes":0x400000,
        "host_x11_frames_with_private_graphics_and_artificial_state":count,
        "minimum_matching_host_optical_sample_points":smallest,
        "distinct_reference_frames":distinct,
        "host_pixels_read_by_real_x11_getimage":True,
        "all_palette_scroll_obj_priority_state_is_synthetic":True,
        "real_ne_xium_guest_nro_executed":False,
        "original_dino_mame_gameplay_executed":False,
        "authentic_gameplay_vram_palette_frame_observed":False,
        "original_dino_inp_wlf_replay_verified":False,
        "physical_nintendo_switch_execution_verified":False,
        "original_rom_derived_graphics_pixels_or_paths_exported":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom",type=Path,required=True)
    parser.add_argument("--sd-root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if (not guard.outside_repo(args.out) or args.out.exists()
                or args.out.is_symlink() or not args.out.parent.is_dir()
                or any(a.is_symlink() for a in args.out.parents)):
            raise ValueError("receipt must be a new external private file")
        result=run(args.rom,args.sd_root)
        code=0
    except Exception:
        # Never print exception text, private paths or original pixel data.
        result={
            "schema":SCHEMA,"status":BLOCKED,
            "host_pixels_read_by_real_x11_getimage":False,
            "real_ne_xium_guest_nro_executed":False,
            "original_dino_mame_gameplay_executed":False,
            "physical_nintendo_switch_execution_verified":False,
            "original_rom_derived_graphics_pixels_or_paths_exported":False,
        }
        code=2
    try:
        guard.write_private_receipt(args.out,result)
    except (OSError,ValueError):
        print(BLOCKED)
        return 2
    print(result["status"])
    return code


if __name__=="__main__":
    raise SystemExit(main())

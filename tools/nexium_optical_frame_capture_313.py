#!/usr/bin/env python3
"""Stage313: optical guest/host frame binding from real NeXium X11 captures.

This module never creates success based on a mock screenshot in CI. A success
requires an actual opt-in NRO process, fourteen guest-written Stage312 scene
rows, fourteen host X11 screenshots with the matching 4-bit optical beacon,
and independent source-scene pixel samples. Screenshots stay temporary.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

try:
    from PIL import Image
except ImportError:
    # The baseline Python CI runs with standard-library dependencies only.
    # The dedicated real X11 workflow installs Pillow explicitly.
    Image = None

try:
    from . import cps1_synthetic_gfx_fixture_308 as graphics
    from . import cps1_private_scene_compositor_parity as scenes
    from . import cps1_frame
    from . import verify_nexium_synthetic_scene_guest_312 as guest
except ImportError:
    import cps1_synthetic_gfx_fixture_308 as graphics
    import cps1_private_scene_compositor_parity as scenes
    import cps1_frame
    import verify_nexium_synthetic_scene_guest_312 as guest

PASS = "NEXIUM_HOST_OPTICAL_14_SYNTHETIC_FRAMES_CONFIRMED"
BLOCKED = "INCONCLUSIVE_NO_NEXIUM_HOST_OPTICAL_SCENE_PROOF"
SCHEMA = "dino-stage313-nexium-optical-scene-14-v1"
# Chosen away from HUD. The actual displayed scene must be visible too.
POINTS = tuple((x, y) for y in (17, 48, 92, 139, 192)
               for x in (29, 93, 168, 237, 323))


def _color(pixel):
    return tuple(pixel[:3])


def _close(p, expected, tolerance=62):
    return all(abs(int(p[i])-int(expected[i])) <= tolerance for i in range(3))


def decode_optical(image):
    """Decode guest index only after TWO actual host-visible locator squares.

    Two magenta squares at known native x positions 8 and 1250 eliminate
    accumulated scale error: estimating host scale from one ~18-pixel square
    alone becomes inaccurate on half-size or antialiased windows.
    """
    im=image.convert("RGB")
    pix=im.load()
    w,h=im.size
    markers={}
    for y in range(1,max(1,h-70),2):
        for x in range(1,w,2):
            p=pix[x,y]
            if not (p[0]>210 and p[1]<75 and p[2]>210):
                continue
            lx=x
            while lx>0 and _close(pix[lx-1,y],(255,0,255),35):
                lx-=1
            ty=y
            while ty>0 and _close(pix[lx,ty-1],(255,0,255),35):
                ty-=1
            key=(lx,ty)
            if key in markers:
                continue
            right=lx
            while right<w and _close(pix[right,ty+1],(255,0,255),35):
                right+=1
            run=right-lx
            if 5<=run<=56:
                markers[key]=run
    values=[(x,y,width) for (x,y),width in markers.items()]
    for lx,ly,width in values:
        for rx,ry,far_width in values:
            if rx<=lx+100 or abs(ly-ry)>max(4,width//4):
                continue
            scale=(rx-lx)/(1250.0-8.0)
            if (not .25<=scale<=3.0 or
                    abs(width-18*scale)>max(4,4*scale) or
                    abs(far_width-18*scale)>max(4,4*scale)):
                continue
            bx=int(round(lx+9*scale))
            bits=0
            ok=True
            for bit in range(4):
                by=int(round(ly+(214-188+9+26*bit)*scale))
                if not (0<=bx<w and 0<=by<h):
                    ok=False
                    break
                rgb=_color(pix[bx,by])
                if _close(rgb,(0,255,0),68):
                    bits|=1<<bit
                elif not _close(rgb,(255,0,0),68):
                    ok=False
                    break
            if ok:
                return (bits,scale,lx-8*scale,ly-188*scale),im
    raise ValueError("two synchronized host optical markers not found")


def verify_optical_image(image,index,reference):
    decoded,im=decode_optical(image)
    frame,scale,origin_x,origin_y=decoded
    if frame!=index:
        raise ValueError("host frame barcode not equal to guest index")
    pix=im.load()
    w,h=im.size
    matched=0
    diversity=set()
    for x,y in POINTS:
        sx=int(round(origin_x+(64+3*x+1)*scale))
        sy=int(round(origin_y+(24+3*y+1)*scale))
        if not (0<=sx<w and 0<=sy<h):
            continue
        expected=reference[4*(384*y+x):4*(384*y+x)+3]
        observed=_color(pix[sx,sy])
        if _close(observed,expected):
            matched+=1
            diversity.add(tuple(expected))
    if matched<10 or len(diversity)<2:
        raise ValueError("host screenshot does not contain independently "
                         "matching synthetic scene pixels")
    return matched


def _window():
    proc=subprocess.run(
        ["xdotool","search","--onlyvisible","--name","NeXium"],
        capture_output=True,text=True,timeout=3)
    if proc.returncode!=0:
        return None
    ids=[s for s in proc.stdout.splitlines() if s.strip().isdigit()]
    return ids[-1] if ids else None


def _capture(wid,destination):
    if Image is None:
        raise ValueError("Pillow required for true host X11 capture")
    subprocess.run(["import","-window",wid,"-silent",str(destination)],
                   check=True,capture_output=True,timeout=8)
    with Image.open(destination) as im:
        return im.convert("RGB")


def _complete_rows(path,index):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>2048:
        return False
    rows=path.read_text("utf-8").splitlines()
    if not rows or rows[0]!=guest.HEADER or len(rows)<index+2:
        return False
    observed=rows[index+1].split(",")
    return len(observed)==4 and observed[0]=="FRAME_SUBMITTED" and (
        observed[1]==str(index))


def _run(exe,nro,sd_root,scratch,deadline):
    # The report can only be accepted from the REAL guest CSV created after
    # framebufferEnd. Exe and NRO must already be cryptographically pinned
    # by the calling workflow.
    from pathlib import Path
    trace=sd_root/"cadillacs-synthetic-scene-guest.csv"
    gfx,_=graphics.build()
    references={}
    env=os.environ.copy()
    with open(scratch/"private-emulator-console.txt","wb") as console:
        with subprocess.Popen([str(exe),str(nro)],stdout=console,
                              stderr=subprocess.STDOUT,env=env) as proc:
            try:
                score=[]
                for i,name in enumerate(scenes.CASES):
                    now=time.monotonic()
                    while not _complete_rows(trace,i):
                        if time.monotonic()>deadline or proc.poll() is not None:
                            raise ValueError("guest row missing or emulator exited")
                        time.sleep(.18)
                    snap=scenes.synthetic_scene(name)
                    reference=cps1_frame.render_frame(
                        gfx,[tuple(x) for x in snap["palette_rgb"]],snap)
                    references[i]=reference
                    matched=0
                    while matched<10:
                        if time.monotonic()>deadline or proc.poll() is not None:
                            raise ValueError("host optical frame not observed")
                        wid=_window()
                        if wid:
                            try:
                                host=_capture(wid,scratch/"host-window.png")
                                matched=verify_optical_image(host,i,reference)
                            except (OSError,ValueError,subprocess.SubprocessError):
                                matched=0
                        if matched<10:
                            time.sleep(.2)
                    score.append(matched)
                    if i<13:
                        # Atomic replace in the isolated fake SD root;
                        # acknowledge only AFTER screen frame i was observed.
                        temporary=sd_root/"cadillacs-synthetic-scene-next.pending"
                        final=sd_root/"cadillacs-synthetic-scene-next.txt"
                        temporary.write_text("NEXT,{}\n".format(i))
                        os.replace(temporary,final)
                actual=guest.validate_text(trace.read_text("utf-8"))
                if actual["status"]!=guest.PASS or len(score)!=14:
                    raise ValueError("missing valid native guest scene parity")
                return {
                    "schema":SCHEMA,
                    "status":PASS,
                    "synthetic_guest_and_host_frames_bound":14,
                    "native_guest_reference_scene_parity":True,
                    "host_optical_frame_identity_all_14":True,
                    "host_scene_pixel_sample_min_matched":min(score),
                    "host_visible_scene_pixels_verified":True,
                    "original_rom_or_gameplay_used":False,
                    "original_gameplay_frame_display_verified":False,
                    "physical_switch_display_verified":False,
                    "private_host_screenshots_uploaded":False,
                    "host_gpu_scanout_timing_verified":False,
                }
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=6)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for required in ("exe","nro","sd-root","summary"):
        parser.add_argument("--"+required,required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        with tempfile.TemporaryDirectory(prefix="dino313-x11-private-") as d:
            result=_run(args.exe.resolve(),args.nro.resolve(),
                        args.sd_root.resolve(),Path(d),
                        time.monotonic()+150)
        code=0
    except (OSError,ValueError,TypeError,subprocess.SubprocessError,
            UnicodeError):
        result={
            "schema":SCHEMA,"status":BLOCKED,
            "host_visible_scene_pixels_verified":False,
            "original_gameplay_frame_display_verified":False,
            "physical_switch_display_verified":False,
            "private_host_screenshots_uploaded":False,
        }
        code=2
    args.summary.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
    print(result["status"])
    return code


if __name__=="__main__":
    raise SystemExit(main())

# Stage321 — private NeXium optical GetImage without xdotool/ImageMagick

## Scope and motivation

Stage320 privately proved 14 host-only X11 images made from authentic
original CPS-1 *static graphics* and deliberately invented game state:
every one of the 25 reference pixels matched in every frame. Those
windows belonged to a Tk diagnostic, **not to NeXium**.

The Stage316 private original-GFX NeXium verifier still invoked two
separate host utilities: `xdotool` (find the window by title/PID) and
ImageMagick `import` (read the X11 pixels). In some environments the
installed ImageMagick binary does not have X11 support. Stage321 replaces
only that private path with Python Xlib, already demonstrated in the
Stage320 host-only proof.

## Implementation

- `tools/nexium_private_xlib_capture_321.py` enumerates up to 512
  mapped X11 windows in at most ten tree levels, with bounded search.
- A visible window must contain `NeXium` in its WM name, expose exactly
  one 32-bit `_NET_WM_PID`, and be owned by the actual launched NeXium
  process or a descendant as checked by Stage319's Linux procfs ancestry.
- Exactly one matching window is required. Stale, unowned, absent,
  malformed, unrelated, hidden or ambiguous windows fail closed.
- The X11 `GetImage` request returns **live server pixels** entirely
  in memory; only 24-bit Xvfb BGRX/padded-32 layout within a bounded
  image size is accepted. Unsupported platforms fail closed.
- The existing independent Stage313 optical verification is unchanged:
  two calibration squares, exact optical frame ID and at least ten of
  25 independently rendered scene pixels must match for each guest
  frame before acknowledging progress. Guest rows remain tied to the
  actual framebuffer submission on the Switch NRO.

**X11 \_NET_WM_PID is supplied by the client** and can be forged by
another process; this is bounded ownership evidence, NOT cryptographic
attestation of the X server, NeXium, or game provenance. The true
original-graphics guest/host optical test is not claimed complete
without executing the pinned NeXium binary.

## Local private usage

Install Python3 dependencies into your private isolated Linux
environment:

```sh
python3 -m pip install Pillow==11.3.0 python-xlib==0.33
```

Install Xvfb and the Mesa Vulkan software driver for running the
NeXium emulator; `xdotool` and ImageMagick are **no longer required**
by Stage316's private original-GFX verifier (Stage313's public
synthetic-only script is unaffected).

From an extracted Stage321 **public-code-only** source package, use
the immutable Stage318 private launcher:

```sh
python3 tools/nexium_private_pinned_optical_launch_318.py \
  --rom /private/roms/dino.zip \
  --nro /private/binaries/verified-stage316-optin.nro \
  --nexium-archive /private/binaries/pinned-ne-xium.tar.gz \
  --receipt /private/evidence/NEW-original-gfx-ne-xium-optical.json
```

Before execution the Stage318 wrapper must pass the pinned NRO and
emulator SHA256 size/hash requirements and source authenticity gates;
the source dino.zip and generated gfx.bin never enter public GitHub.
The resulting local receipt, if any, contains only aggregate proof
without original game assets or screenshots. All original ROM hashes
and private paths remain private.

## Public CI and evidence limits

The Stage321 workflow installs Pillow and python-xlib, creates an
**invented** Tk window in a REAL Xvfb server, stamps it with its actual
client PID, locates it by this exact process and reads server pixels
back with Xlib. It also tests forged/missing/stale/ambiguous X11
ownership using mocks, compiles the existing source-only C compositor,
and uploads only public C/H/Python source.

No original game ROM, original graphic frames, screenshots, private
user files, Nintendo firmware/keys or copyrighted media enter
GitHub CI. A passing public workflow proves Xlib captures and
process binding for invented images, **not NeXium execution or actual
arcade gameplay**. Historical original MAME INP/WLF playback, game
VRAM/palette registers, physical Nintendo Switch display, audio,
gameplay correctness and licensing remain unverified.

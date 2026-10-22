# Stage320 — original static CPS-1 graphics, real HOST X11 pixels, no NeXium

Stage317 established exact C/Python compositor parity for all 14
invented scene states using the user's source-verified original static
CPS-1 graphics: 1,204,224 RGBA pixels matched, no mismatches.
Stage319 tightened the private NeXium optical window locator to require
the correct launched emulator process, not merely a matching title.

On the local private Linux test host, NeXium itself could NOT be
launched because its pinned public binary and software Vulkan driver
were not installed. The preinstalled ImageMagick `import` utility also
lacks X11 delegate support. Instead of claiming a NeXium guest proof,
Stage320 isolates and tests only the **REAL host X11 pixel readback**.

## Local private experiment already observed

Using the original user-owned `Cadillac Dinosaur.zip`, all sixteen MAME
0.106 ROM members were checked against the historical public source
CRC32+SHA-1 and canonicalized privately. The correct 4,194,304-byte
graphics region was reconstructed in memory. For every one of the 14
deliberately artificial Stage305/307 scene states:

1. Independent Python generated a 384x224 RGBA scene using **real
   original static graphics** and **invented** palette, OBJ, tilemaps,
   priority and scroll state.
2. A local Tk GUI presented it at 3x in an actual 1280x720 virtual X11
   window, with Stage313's two magenta calibration markers and a
   per-scene four-bit frame barcode, outside the CPS-1 viewport.
3. `python-xlib` issued a genuine `GetImage` request against the
   window's XID and received X server pixels (not a copy of the input
   Python image). Pillow decoded the 24-bit Xvfb BGRX response.
4. The unchanged Stage313 `verify_optical_image` decoder independently
   checked both markers, the correct frame number and all 25 selected
   reference scene pixels.

**Measured result: 14/14 X11 window frames and 25/25 matching reference
points in EVERY frame**. No original pixels or screenshots were added
to public GitHub, chat reports, CI artifacts or releases. Source ROM
and derived graphics remained in external private temporary storage.

This is genuine X11 host-visible evidence, but the window belongs to
an independent local Tk program, NOT the NeXium emulator or a
Nintendo Switch NRO. The private optical gate of Stage316/319 remains
UNVERIFIED until the pinned NeXium guest is actually executed.

## Reproduce using only private local originals

The new public-source-only utility
`tools/cps1_private_original_gfx_host_x11_320.py` requires:

- A canonical, source-verified private `dino.zip` from Stage299
- Stage315's private SD tree with byte-exact `gfx.bin` and `sequence.bin`
- Python3 with `tkinter`, `Pillow` and `python-xlib`
- Linux x86_64 with Xvfb supporting 1280x720x24, BGRX on the 32-bit
  transfer representation

Run only in an isolated private directory. The output JSON file must
be NEW and outside the Git checkout:

```sh
xvfb-run -a -s "-screen 0 1280x720x24" \
  python3 tools/cps1_private_original_gfx_host_x11_320.py \
    --rom /private/roms/dino.zip \
    --sd-root /private/output/stage315-new-sd \
    --out /private/evidence/stage320-NEW-private-host-only.json
```

Before any host frame is rendered the Stage316 private source gate
checks all 16 original ROM checksums and requires the SD region to
match the ROM exactly and the sequence to equal the canonical 14
artificial scenes. It refuses unsafe symlinks, public-tree source
paths, stale receipts, non-Xvfb pixel formats, wrong host frame
barcodes or even one mismatching sample point. On success a 0600
aggregate-only receipt uses the status:

`PRIVATE_ORIGINAL_GFX_REAL_HOST_X11_14_OF_14_OPTICAL_CONFIRMED_NOT_NE_XIUM`

It explicitly sets `real_ne_xium_guest_nro_executed=false`,
`original_dino_mame_gameplay_executed=false`,
`physical_nintendo_switch_execution_verified=false` and
`original_rom_derived_graphics_pixels_or_paths_exported=false`.

## Public CI

`.github/workflows/cps1-private-original-gfx-host-x11-320.yml`
runs only invented gradient scene image tests of the common optical
calibration and strict failure rules, compiles public C code, checks
ROM-free Git provenance and outputs an updated PUBLIC source-only ZIP.
No original `dino.zip`, derived 4MiB `gfx.bin`, original image,
X11 capture, raw trace or Nintendo firmware is made public.

## Evidence boundaries

- **Proven:** original STATIC graphics provenance by source MAME hashes;
  C/Python parity on invented game state; host-only X11 presentation and
  pixel readback on that original graphics + artificial state.
- **Not proven:** original Cadillacs and Dinosaurs game executable running;
  original gameplay palettes/VRAM/OBJ positions; original INP/WLF replay;
  original audio, input timing or gameplay equivalence; output of those
  graphics by the NeXium guest or physical Nintendo Switch.

The next meaningful gate is still Stage316/319's **actual pinned
NeXium process**, successful 14 guest submissions and 14 real
process-bound X11 captures. A Tk window must never be substituted
for that result.

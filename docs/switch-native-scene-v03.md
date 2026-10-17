# Native CPS-1 scene compositor — Nintendo Switch v0.3

This milestone runs a **partial CPS-1 scene renderer natively on Switch**
rather than displaying a screenshot rendered beforehand.

The app reads user-provided interleaved graphics `gfx.bin` and an optional
**single coherent video-memory snapshot** `scene.bin` from SD. The C engine
reconstructs all three CPS-1 tilemap layers (8×8, 16×16, 32×32), horizontal/
vertical tile flips, scroll offsets, per-line Scroll2 rowscroll, sprite object
tiles/blocks, 4-bit pen indices, active palette RGB and QS2 priority masks.

A 384×224 RGBA image is constructed **on the Switch CPU** and then scaled
3× using nearest-neighbor pixels to 1152×672 inside a 1280×720 framebuffer.
Press **X** to switch between the previous tile browser and the composed scene.

## Runtime files

Place on an SD card:

```text
switch/cadillacs-dinosaurs-switch/
  cadillacs-dinosaurs-switch.nro
  gfx.bin       # user's own graphics ROM region: exactly 4,194,304 bytes
  scene.bin     # optional captured (or synthetic test) single frame
```

Create the graphics region on a computer from personally held ROM files:

```sh
python3 tools/cps1_gfx.py /private/dino.zip --out-local gfx.bin
```

Convert an *existing coherent frame snapshot* from `tools/cps1_capture.py`
or a compatible JSON to the compact binary format:

```sh
python3 tools/cps1_scene_export.py /private/frame_snapshot.json --out scene.bin
```

The exporter **requires `palette_rgb` containing all 3072 effective RGB
entries** copied from runtime palette RAM. Merely using current graphics-RAM
palette source does not capture palette latch history. The exporter refuses
such incomplete captures instead of claiming authentic original colors.

## Portable binary layout

`scene.bin` is `62,510` bytes, little-endian, format version 1.

- 8-byte ASCII magic `CPS1SCN1`;
- 32-bit payload length `62494`;
- 32-bit CRC32 of payload;
- layer-control and video-control (two 16-bit words);
- 3 scroll X values and 3 scroll Y values (16-bit words);
- three enabled flags and one required zero byte;
- four priority mask registers; rowscroll source index offset;
- 3072 RGB triples (8-bit channels);
- 3 x 8192 tilemap words (code and attributes);
- 1024 VBlank-latched OBJ RAM words;
- 1024 rowscroll words.

No ROM bytes are embedded into the scene file, but gameplay RAM,
palette and captured images may contain copyrighted visual information.
Do **not** commit runtime captures, gfx.bin or extracted images to GitHub.

The C loader rejects invalid magic, length, CRC, and malformed header. The
engine treats pen 15 as transparent and uses the `CD63B` mapping rules
for `dino` (World 930201) only.

## Testing

```sh
python3 -m unittest discover -s tests -v
make -j2
```

`tests/test_cps1_scene_native.py` compiles the **same C source used by
Switch** into a Linux shared library and compares exact RGBA output to the
existing independent Python reference implementation across synthetic
frame conditions. Tests include code bank placement, color and sprite
composition, priority occlusion, scanline scrolling and CRC integrity.

No real MAME video snapshot was available when the module was authored;
therefore the new scene is still **not claimed pixel-exact to the arcade
game**. MAME capture + synchronized parity comparison remain necessary.

## Not yet implemented

- Sound/interactive gameplay, AI and player collision.
- Per-subframe raster writes; sprite one-frame latency is handled by requiring
  a *latched* buffer from the capture rather than emulating the latch clock.
- Global flipscreen, star layers, every complex CPS-1 transparency priority
  edge case or emulator-grade device/register synchronization.
- HD asset restoration. This remains a crisp native playback of original
  4-bit indexed graphics, not newly drawn HD art.
- Validation on physical Switch hardware.

## Stage 99 — shared CPS-1 native multi-size tile decoding

The native Switch scene renderer now delegates Scroll1/2/3 planar pixel
extraction to `cps1_tile_pixel()` in the same portable `source/cps1_tile.c`
used for 16x16 sprites. This removes duplicate and potentially drifting
ROM address/4-bit plane decode logic from `source/cps1_scene.c`.
Separate native APIs `cps1_decode_tile8()` and `cps1_decode_tile32()`
cover background tile sizes in addition to the existing 16x16 routine.
Scroll1's tilemap-index bit 5 selects the left or right 4-byte half-row;
strict bounds checks reject invalid geometry or unmapped tile codes.
A failed tile read stays transparent in the scene renderer.

The new opt-in `tools/cps1_private_multisize_tile_parity.py` operates
only on a **user-owned local** original dino ZIP:

~~~sh
python3 tools/cps1_private_multisize_tile_parity.py /private/owned/dino.zip
~~~

It interleaves eight local graphics lanes into a 4-MiB CPS-1 region
**in RAM only** and compares independently decoded 8x8-left,
8x8-right, 16x16 and 32x32 pen indices with the same native C
implementation used by the Switch renderer. Selection includes
beginning/end, exact graphic-bank seam, even intervals and reproducible
pseudorandom codes. The output includes only aggregate match counts,
never private paths, SHA-256 hashes, original pixel data or extracted ROMs.

The privately supplied original dino ZIP yielded **1,539 sampled tile
variants**, **538,368 compared pen indices**, and **zero mismatches**.
All sixteen 4-bit pen values were observed in every variant. Public CI
runs 100% synthetic fixtures, catches deliberate reference-decoder
errors, and exercises malformed ZIP and native out-of-range refusals.

**Limitation:** this result verifies the sampled indexed tile-decode
operations, not a game frame. It does not establish correct CPS-1
runtime palette, tilemap VRAM, row-scroll timings, sprite buffering,
VBlank, MAME game execution or Nintendo Switch hardware pixel parity.
Original ROM contents and any raw derived sprites/scenes are not
included in the public repository or CI.

## Stage 100 — compare the actual native Switch compositor with controlled video state

The first private **scene-level** parity tool is now available:

~~~sh
python3 tools/cps1_private_scene_compositor_parity.py /private/owned/dino.zip
~~~

It reads the eight original, privately held CPS-1 graphics ROM lanes
**locally and in RAM**, builds the same `source/cps1_scene.c` plus
`source/cps1_tile.c` used in the technical Nintendo Switch NRO as a
temporary host library, and compares complete **384×224 RGBA frames**
with the separately implemented Python `tools/cps1_frame.py` compositor.
Four completely **synthetic control states** exercise layer ordering,
Scroll1/2/3 tilemap placement, RGB palette pages and sprite colors,
priority-mask sprite occlusion, transparency, horizontal/vertical flips,
composite and overlapping sprites, viewport clipping and Scroll2
rowscroll near a 1024-entry wrap.

The original game contributes **only its graphics tile data**, never
original video state, palette RAM or an emulator-captured frame.
No private game pixels, screenshots, ROM contents, raw CRC/SHA values,
user paths or generated RGBA frames are written out or sent to GitHub.
The JSON includes fixed statuses and per-scenario aggregate mismatch
counts only; public Actions run on fabricated eight-lane ZIP fixtures.
An intentionally corrupted reference renderer is required to fail,
guarding against accidental always-pass comparisons.

Successful parity therefore supports *internal C/Python compositing
consistency for these controlled scenes*, **not** reproduction of an
original `dino` frame, MAME gameplay/VBlank accuracy, real palette
history or Switch hardware framebuffer equivalence. The current
MAME 0.289 ROM audit limitations remain unchanged.

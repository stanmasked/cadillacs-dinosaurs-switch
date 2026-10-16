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

# CPS-1 dino physical screen geometry and MAME tile-map addressing

Stage 22 focuses on where previously verified decoded tiles are **placed**
in the raster, not whether the 4-bit graphics are correctly decoded.

## Verified geometry contract from original MAME source

Native CPS-1 raster is 512x256. MAME's visible `dino` area used by our
scene exporter is **physical X=64..447, Y=16..239** (384x224).
The portable renderer's output coordinate (0,0) therefore represents
physical hardware pixel (64,16), not (0,0).

MAME `src/mame/capcom/cps1_v.cpp`, specifically
`tilemap0_scan`, `tilemap1_scan`, `tilemap2_scan`,
`screen_update_cps1` and the three tilemap declarations in `video_start`,
provides these layouts:

| Layer | Tile side | Raster map dimensions | RAM word index of code |
| --- | ---: | --- | --- |
| Scroll1 | 8 px | 64x64 | `2*((row & 31) + (col << 5) + ((row & 32) << 6))` |
| Scroll2 | 16 px | 64x64 | `2*((row & 15) + (col << 4) + ((row & 48) << 6))` |
| Scroll3 | 32 px | 64x64 | `2*((row & 7) + (col << 3) + ((row & 56) << 6))` |

Each tile entry uses two 16-bit RAM words: code and attributes.
Scroll1 uses the tile-map index's bit 5 to alternate left/right 8x8
halves of the same 64-byte graphics code. Scroll3 masks the tile code
to 14 bits. Horizontal/vertical attribute flip bits are 5 and 6.

For a displayed screen pixel, compute the world position by adding
horizontal/vertical scroll registers and masking into the 512, 1024 or
2048-pixel tilemap width. For Scroll2 with line scrolling enabled,
the original screen line `y` uses `rowscroll[(y + offset) & 1023]` as
an extra horizontal delta. The effect applies **only to its scanline**.

## Independently inspect a pixel's source tile

`tools/cps1_geometry_probe.py` determines the tilemap cell, RAM offset,
code, attributes, source pixel position (including tile flip),
Scroll1 half selection, palette group and priority group **without
decoding a single graphics ROM byte**.

```sh
python3 tools/cps1_geometry_probe.py /private/frame-snapshot.json \
  --layer scroll2 --x 64 --y 16 \
  --out /private/probe-scroll2-top-left.json
```

The `--x` and `--y` flags use the **512x256 hardware raster**
coordinates, not positions relative to the cropped 384x224 PNG.

Useful fixed oracles:

- Scroll1 screen pixel (64,16), zero scroll: cell (8,2), tile index
  258, RAM word index 516, left half of its graphics code.
- Scroll1 pixel (72,16): cell (9,2), index 290, **right** half.
- Scroll2 screen pixel (64,16), zero scroll: cell (4,1), index 65.
  Increasing scrollx by 16 reaches (5,1), index 81.
- Scroll3 with scrollx=1984: pixel (64,16) maps to world X=0
  after the 2048-pixel wrap; pixel (96,16) moves to column 1.
- A single sprite placed at physical (447,239) with a solid pen is
  visible in **exactly the bottom-right output pixel**.

## Tests and current verification

`tests/test_cps1_geometry_probe.py` contains 7 regression tests,
including source-independent predictions checked against our Python
renderer with two distinct, non-ROM 8x8-half colors and controlled
Scroll2 line scrolling.

`tests/test_cps1_scene_native.py` additionally contains four new
C-versus-Python full-scene regression scenarios exercising hardware
clip boundaries, alternating 8x8 halves, a selected raster line, and
Scroll3 wrapping.

A separate local Python run confirmed **5 representative placements**
with synthetic tile graphics; its JSON report is available privately.
The new GitHub C full-scene tests need a runner to execute before
native end-to-end geometry parity can be claimed for this revision.

## What remains unverified

These deterministic samples constrain origin/camera geometry only.
They do NOT prove runtime pixel matching with real MAME, sprite latency,
the emulator's partial raster updates, hardware flipscreen, priority
interaction in all scenes, or Nintendo Switch gameplay.

Original MAME reference:
https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp

All original game data and captured frame snapshots must stay local.

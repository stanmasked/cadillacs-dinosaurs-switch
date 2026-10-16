# CPS-1 partial frame compositor — World 930201

Implementation: `tools/cps1_frame.py`. Supported game board: **dino / CD63B / CPS-B-21 QS2**.

## What this stage proves

The tool can construct a **384 x 224** RGBA reference framebuffer, using the source graphics ROM region plus a *separately supplied* runtime video RAM snapshot.

MAME sources:

- [CPS1 video driver](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp): `tilemap0_scan`, `tilemap1_scan`, `tilemap2_scan`, `get_tile*_info`, `find_last_sprite`, `cps1_render_sprites`, `render_layers`.
- [CPS1 hardware constants](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1.h): 512-pixel raster, visible rectangle **x=64..447, y=16..239**.

A 64 x 64 tilemap uses 4096 tile entries (8192 16-bit words): one tile code and one attributes word per entry. All three layers use different custom RAM scanners:

```python
scroll1 = (row & 31) + (col << 5) + ((row & 32) << 6)
scroll2 = (row & 15) + (col << 4) + ((row & 48) << 6)
scroll3 = (row &  7) + (col << 3) + ((row & 56) << 6)
```

For each tile, attr low five bits select the palette color group, bits 5/6 flip X/Y. For scroll1, tilemap-index bit 5 selects either `8x8-left` or `8x8-right` graphics layout. For scroll3, the raw tile code is masked with `0x3fff`.

Layer order is decoded from CPS-B layer-control register bits 6, 8, 10 and 12 (four two-bit fields, back to front). Sprite RAM is the **already VBlank-buffered** OBJ RAM, each entry being `[x,y,code,attributes]`; an attribute with high byte `0xff` ends the list. Block size, flips and per-sprite color groups are processed using the dino CD63B mapper. Pen 15 is treated as transparent.

## Snapshot format

The tool accepts a local JSON snapshot:

```json
{
  "layer_control": 2496,
  "palette_source": {
    "control": 1,
    "words": ["replace with 512 numeric 16-bit palette words"]
  },
  "scroll2": {
    "words": ["replace with 8192 numeric 16-bit RAM words"],
    "scrollx": 0,
    "scrolly": 0,
    "enabled": true
  },
  "buffered_obj_words": [64, 16, 512, 0, 0, 0, 0, 65280]
}
```

**Important:** The example above is schematic. Actual `words` entries must be numbers, not explanatory strings. The `palette_source` option emulates an isolated CPS-B palette copy from gfx RAM. For an accurate mid-game state, prefer `palette_rgb`: an array of exactly **3072 [R,G,B] triples from *effective* hardware palette RAM**, including previously retained pages. You may include `scroll1`, `scroll2`, and/or `scroll3`; omitted tilemaps are not rendered. Each supplied scroll layer must have **8192 numeric words**.

Run on local ROMs and RAM snapshots only:

```sh
python3 tools/cps1_frame.py /private/dino.zip /private/frame_snapshot.json \
   --out local_outputs/reference_frame.png
python3 -m unittest discover -s tests -v
```

To capture a real frame, instrument an authorized local MAME runtime near `screen_update_cps1` / `cps1_get_video_base` and export: **effective palette RGB, all enabled scroll RAM tile/code pairs, the three scroll offsets, CPS-B layer-control word, layer enable state, and latched OBJ RAM**. Avoid collecting buffers at inconsistent times; the MAME OBJ buffer is latched at VBlank and may be one frame behind mutable OBJ RAM.

## Explicit missing behavior — NOT pixel-perfect MAME yet

- Partially addressed: QS2 priority-register high pens can occlude sprites immediately above a scroll layer. Complex reference edge cases still require replay validation.
- Partially addressed: per-line Scroll2 rowscroll is supported with static 1024-word RAM, but mid-frame raster events remain unsupported.
- Flipscreen, starfields and dynamic changes during a frame.
- Partial CPS-A/CPS-B decode and enabled-layer flags are supplied by tools/cps1_capture.py from raw binary memory dumps; the renderer still accepts manually supplied snapshot state.
- MAME-specific sprite clipping edge cases and video capture synchronization.

Therefore the tool is a **partial diagnostic renderer, not an emulator and not a runnable HD-remake**.

## Validation (2026-10-16)

- All **68 / 68** local Python tests now pass: the original 50, 13 raw capture/raster helper tests and 5 render priority/rowscroll tests.
- A local integration run with the user's `dino.zip` produced a 384 x 224 diagnostic PNG using **synthetic RAM and synthetic palette**. The graphics ROM SHA-256 remains `68786de27105ccc64f28f66ad1025f2e6f521aa60ab35c489fb0baaaa8679de1`.
- Neither ROM data, extracted assets, captured RAM nor the local diagnostic image is committed to this repository.
- Native Switch boot and GitHub Actions completion remain **unverified**; a separate NRO build workflow is now configured.

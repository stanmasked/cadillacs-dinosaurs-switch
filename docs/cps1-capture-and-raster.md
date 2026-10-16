# CPS-1 raw memory capture and partial replay — dino World 930201

**Status (2026-10-16):** New raw-dump adapter, CPS-B priority pen selection and Scroll2 line scroll implemented. 68/68 local Python tests pass. An end-to-end local run converted *synthetic* raw dumps into a snapshot JSON and rendered **384 × 224 RGBA PNG** with the user's own World 930201 ROM as the pixel source. This is **NOT a live game capture**.

## Evidence and MAME source

The dino row of MAME [cps1_v.cpp](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp) specifies **CPS_B_21_QS2, mapper_CD63B**. The QS2 register definition (reference blob SHA `c1b5e3867824d0d1877b981142db7741346d2c55`) maps:

| Register | CPS-B byte offset |
|---|---:|
| Layer control | 0x0a |
| Priority masks (groups 0..3) | 0x0c, 0x0e, 0x00, 0x02 |
| Palette copy control | 0x04 |
| Layer enable masks (all three tilemaps) | 0x16 |

The frame converter uses CPS-A offsets:

- 0x02, 0x04, 0x06: Scroll1/2/3 graphics RAM bases.
- 0x08: additional/rowscroll RAM base.
- 0x0a: palette source RAM base.
- 0x0c/0x0e, 0x10/0x12, 0x14/0x16: three horizontal/vertical scroll register pairs.
- 0x20: Scroll2 rowscroll source index offset.
- 0x22: video control (bit 0 = Scroll2 rowscroll; bits 2/3 additionally gate Scroll2/3).

**Graphics RAM** is 0x40000 bytes. Scroll RAM blocks are aligned to 0x4000 bytes; the other/rowscroll buffer is aligned to 0x800 bytes, and the palette source is aligned to 0x400 bytes. MAME's `cps1_base` masks the byte offset into 0x40000.

## Raw dump files (local only)

Provide four **coherent, binary snapshots** from a running, authorized CPS-1 instance. MAME itself is NOT invoked by our adapter, and was not available in the analysis environment.

| Filename example | Exact size | Contents |
|---|---:|---|
| `gfxram.bin` | 262,144 bytes (0x40000) | CPS-1 graphics RAM (not graphics ROM) |
| `cps_a.bin` | 64 bytes (0x40) | CPS-A register RAM |
| `cps_b.bin` | 64 bytes (0x40) | CPS-B register RAM |
| `buffered_obj.bin` | 2,048 bytes (0x800) | **VBlank-latched** object RAM, not current mutable object RAM |

The binary files contain unsigned 16-bit words; specify **exact word endianness** with `--endian big` or `--endian little`. Arbitrarily dumping host-native memory and then assuming 68000 big-endian is unsafe: use the endianness of the *actual bytes exported*.

Optional: `effective_palette.json`, a JSON array of **3072 [R,G,B] values** (8-bit channels) captured from MAME's *effective hardware palette*, not from static ROM or merely the current graphics RAM. For an accurate colored frame, this effective palette capture is essential: the CPS-B copies the source palette only when CPS-A palette-base is written, so some pages may contain older values.

Run:

```sh
python3 tools/cps1_capture.py \
  --gfxram /private/gfxram.bin \
  --cps-a /private/cps_a.bin \
  --cps-b /private/cps_b.bin \
  --buffered-obj /private/buffered_obj.bin \
  --endian big \
  --effective-palette /private/effective_palette.json \
  --out local_outputs/frame_snapshot.json

python3 tools/cps1_frame.py /private/dino.zip local_outputs/frame_snapshot.json \
  --out local_outputs/partial_game_frame.png

python3 -m unittest discover -s tests -v
```

If `--effective-palette` is omitted, the tool still works but marks its inferred palette as **`approximate_current_source_not_latched`**. Do not describe these colors as original/certified.

## Newly supported effects

- Scanline-based Scroll2 X offset with 1024-word rowscroll table, index `(screen_y + CPS_A_ROWSCROLL_OFFS) & 0x3ff`, enabled by CPS-A video control bit 0.
- Tile high-priority pens from QS2 CPS-B priority registers. Pens for tile attribute groups 0..3 can **occlude sprites**, when the corresponding tilemap is directly below sprites in the draw order. Pen 15 remains transparent.
- Registration of layer enables and CPS-A X/Y scroll values from raw register dumps; the renderer still only performs a **static partial frame**.

## Limitations before pixel-perfect screenshots

- No MAME or live hardware execution/capture in the current environment.
- No captured actual stage palette/VRAM/latched OBJ memory supplied yet; diagnostic generated from artificial RAM only.
- No star layers, global flipscreen, sub-frame raster writes or fully modeled sprite latency.
- The rowscroll support is per scanline from one coherent snapshot, *not* a raster interrupt/event timeline.
- Priority behavior is modeled for the immediate tilemap-below-sprites case; exact priority-map edge cases and scroll tile transparency groups need reference-frame comparison.
- This is neither a complete arcade emulator nor a playable Switch build.

No ROM, binary RAM dump, original extracted game sprites or rendered original game art are stored in GitHub.

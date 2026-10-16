# CPS-1 native planar graphics layout parity

This change unifies all graphics tile decoding in portable
`source/cps1_tile.c/.h`, shared by the Switch-native scroll renderer
and its 16x16 tile viewer. The library now exposes:

| API | Tile geometry | CPS-1 source | Bytes/code |
| --- | --- | --- | ---: |
| `cps1_decode_tile8` | 8×8, left / right | Scroll1 | 64 |
| `cps1_decode_tile16` | 16×16 | Scroll2 and sprites | 128 |
| `cps1_decode_tile32` | 32×32 | Scroll3 | 512 |
| `cps1_read_tile_pen` | single 4-bit palette index | Any of above | — |

The 8×8 scroll tile halves use the same 64-byte code with an additional
four-byte horizontal offset; `tile_index & 0x20` selects the right
half. Pixel planes are ordered at bit offsets 24,16,8,0, with most
significant bit first within each horizontal 8-pixel group. Returned
pixels are **palette indices 0–15**, not invented RGB colors.

All four APIs reject invalid pointers, tile dimensions and out-of-range
codes. Output buffers stay unchanged on rejected calls. The existing
`CPS1SCN1` and `CPS1SEQ1` binary formats are not modified.

## ROM-free CI tests

- `tests/test_cps1_native_layouts.py` compiles the actual C library
  and compares every tile in a seeded, artificial graphics fixture
  against independent Python `decode_tile`, for **all four layouts**.
- `tests/test_cps1_native_gfx_audit.py` verifies deterministic sampling,
  malformed input handling and private audit results.
- Existing native full-scene parity tests validate drawing layers and
  sprites through the newly shared pixel path.

No game ROM or extracted graphics are committed to source control.

## Independent offline audit with your own dino ROM

After creating the graphics region privately via the existing exporter,
run from the repository root:

```sh
python3 tools/cps1_native_gfx_audit.py /private/gfx.bin \
  --samples 1024 --output /private/cps1-gfx-layout-audit.json
```

The tool compiles the same portable C code, compares its tile output
byte-for-byte to the Python reference for 1024 reproducibly chosen codes
per format (including representative range endpoints and center), and
writes only counts and SHA-256 sample digests. It never uploads files
or stores original ROM byte streams in the report.

On the privately supplied original **dino** graphics region, local
pre-integration inspection covered:

- 1,024 Scroll1 left 8x8 codes: 65,536 pixels, zero mismatches;
- 1,024 Scroll1 right 8x8 codes: 65,536 pixels, zero mismatches;
- 1,024 Scroll2/sprite 16x16 codes: 262,144 pixels, zero mismatches;
- 1,024 Scroll3 32x32 codes: 1,048,576 pixels, zero mismatches.

In total **1,441,792 original ROM tile pixels matched**.
This validates the chosen tile samples and native decoder, **not**
the rendering order, animation timing, runtime effective palette,
sprites vs MAME frame parity, or actual Nintendo Switch operation.

MAME source references:
[graphics layouts](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1.cpp)
and [CPS-1 video renderer](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp).

Native NRO builds remain dependent on GitHub Actions; hardware testing
and a real synchronized MAME gameplay capture are still outstanding.

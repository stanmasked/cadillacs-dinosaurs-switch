# Stage 36 — faster byte-exact CPS-1 flipscreen in the Python diagnostics

## Scope

This is a ROM-free diagnostic compositor optimization, **not** a new
gameplay component or Switch renderer change. It stacks on draft PR #19,
which introduces `VIDEO_CONTROL` bit 15 global flipscreen in the native
and Python renderers.

Previously `render_frame` reversed RGBA pixels with one Python slice
assignment per pixel. A full CPS-1 visible frame has 384×224 = 86,016
pixels, so this added per-pixel interpreter overhead even after
the source view had been composited.

## Optimized operation

`tools/cps1_frame.py::_rotate_rgba_pixels_180` treats each RGBA quadruplet
as an *opaque*, native 32-bit unsigned integer, reverses the
`memoryview(...).cast('I')` element sequence, then writes those elements
back to bytes. Converting into and out of a native word does **not**
swap individual R/G/B/A bytes: the exact original bytes of a single
pixel remain in the same order on both big- and little-endian hosts.

For unusual Python targets whose native C `unsigned int` is not
four bytes, it falls back to explicit four-byte pixel chunks.
Malformed inputs whose byte length is not divisible by four are rejected.

The hardware-coordinate transformation itself, the 512×256 bounding
contract, tile/scenery decoding, OBJ priority and native C renderer
are **unchanged**. The optimized helper only reorders completed pixel
positions in the final Python RGBA buffer.

## Isolated performance check

On one local Python environment, using a synthetic 384×224 4-channel
byte buffer (without any game ROM, layer decoding or MAME), a simple
four-run wall-time check gave approximately:

| Rotation method | Isolated per-frame work |
|---|---|
| Previous Python per-pixel slice loop | ~50–57 ms |
| 32-bit `memoryview` reversal | ~0.5–2.7 ms |

This is an **illustrative local microbenchmark**, not a reproducible
end-to-end performance claim, not a native Switch measurement and not
a claim about the complete frame-composition time.

## Regression coverage

`tests/test_cps1_flipscreen_rotation.py` adds five ROM-free tests:

1. Pixel-channel exactness on asymmetric RGBA across odd and even sizes,
   including a 384×224 frame; involution (rotate twice = original).
2. Original mutable input remains unmodified.
3. Fallback branch when the native integer width is not four bytes.
4. Reject partial RGBA pixels.
5. Verify a colored synthetic sprite over Scroll2 reflected from the
   *physical* 512×256 raster into a noncentral 44×34 crop, with an
   independent slow byte-preserving oracle.

**Verification boundary:** An isolated transformation microbenchmark
checked equality against the prior formula, but the new committed
test suite and the full source branch have **not been confirmed by
GitHub CI**. Action jobs were failing before runner allocation;
see issue #20. No original captures, tiles, ROMs or binaries were
published. Keep this stacked PR in draft until independent checkout
and tests run.

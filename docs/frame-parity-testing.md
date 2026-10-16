# Pixel-exact comparison against MAME frame references

The ROM-only graphics extraction does not establish that the composed frame
matches the original arcade game. `tools/frame_compare.py` is an independent,
ROM-free image comparator for this specific verification gap.

## What it does

- Reads 8-bit noninterlaced **RGBA PNG** images with all standard scanline
  filters (0, 1, 2, 3, 4); validates chunk CRC and image dimensions.
- Strictly validates PNG chunk structure: `IHDR` first, optional `PLTE`
  only before `IDAT`, consecutive `IDAT` data, empty `IEND` and no
  trailing data. Rejects invalid chunk type names or unknown *critical*
  chunks instead of silently comparing potentially ambiguous inputs.
  Valid ancillary chunks and split consecutive `IDAT` segments remain allowed.
- Compares pixels in raster order with an optional `--ignore-alpha` switch.
- Reports integer differing pixel count, fraction of differing pixels,
  mean absolute channel error, peak channel error and first mismatched (x, y).
- Creates a grayscale-to-red **absolute-error heatmap** via `--diff`. Red
  channel represents maximum per-channel difference (0..255), black = exact.
- Returns process exit code 0 when mismatch count is within
  `--max-different-pixels`, 1 when it exceeds tolerance, and 2 for errors.

No commercial ROM, game assets or MAME memory dumps are stored in GitHub.
Comparisons run on local images; **do not treat synthetic reference frames as
verified original gameplay screenshots**.

## Usage

```sh
python3 tools/frame_compare.py /private/mame_frame.png \
   /private/cps1_recreated.png \
   --diff local_outputs/pixel_error_heatmap.png

# Strict CI gate: fail if even one pixel differs
python3 tools/frame_compare.py /private/mame_frame.png \
   /private/cps1_recreated.png --max-different-pixels 0

# Compare RGB only if alpha channel semantics differ by capture path
python3 tools/frame_compare.py /private/mame_frame.png \
   /private/cps1_recreated.png --ignore-alpha
```

Images must be captured at the **same game frame**, with matching crop,
palette state, active layers, input state, sprite latch timing, and flip-screen.
If dimensions differ, the tool fails explicitly rather than implicitly
scaling one frame. Pixel-exact comparisons require same coordinate system and
color conversion.

## Technical validation

Nine new unit tests cover all five PNG filters, round-trip of the project's
existing PNG writer, identical and mismatching frame metrics, alpha exclusion,
truncated/corrupt PNGs, and unsupported pixel formats.

A local 384×224 synthetic diagnostic frame was compared to an identical copy:
**86,016/86,016 pixels matched**. Two different diagnostic images were also
compared to exercise a nonzero error report. These are functional QA checks,
not a MAME authenticity verdict.

This stage complements the previously developed partial CPS-1 video
renderer. Remaining requirements: actual synchronized MAME capture, complete
priority/raster implementation, frame parity, and real Switch runtime.


## Stage 37 — strict PNG evidence handling

The structural checks above prevent a false sense of verified reference
integrity: a CRC-valid but malformed PNG must not be accepted as a valid
MAME or native-renderer comparison input. New ROM-free coverage in
`tests/test_frame_compare_png_structure.py` includes nine methods for
trailing bytes, out-of-order and nonconsecutive chunks, invalid PNG
type names, unknown critical payloads, malformed `IEND`, misplaced
palette chunks, and preservation of legitimate ancillary and adjacent
`IDAT` chunks.

The safety limit on dimensions (8192×8192) and the existing filtered
RGBA decode and pixel metrics are unchanged. This is format validation,
**not proof of gameplay-frame provenance**, and does not turn synthetic
frames into authentic MAME reference captures.

A separately reproduced local chunk-state checker exercised malformed and
valid synthetic fixtures. The exact newly committed GitHub test suite
has not yet run successfully in Actions because its runner allocation is
failing before job steps (issue #20); this PR remains a draft pending CI.

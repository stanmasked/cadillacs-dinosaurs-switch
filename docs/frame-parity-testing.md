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


## Stage 38 — diagnose frame registration without weakening parity

In the original 384×224 CPS-1 viewport, even a one-pixel camera offset
makes a large number of otherwise correct colors disagree. An optional
diagnostic scan can distinguish such **alignment** problems from color,
tile and sprite errors:

```sh
python3 tools/frame_compare.py /private/mame_frame.png \
  /private/cps1_recreated.png --diagnose-shift 2
```

`--diagnose-shift N` searches candidate offsets from `-N` to `+N`
on both axes (N=1..4; default 0 disables scanning). The meaning of
`dx=+1,dy=-1` is: compare reference pixel `(x,y)` against candidate
pixel `(x+1,y-1)`. Only **actual overlapping** source coordinates
contribute: there is no wrapping, edge cloning or synthetic background.
The JSON `translation_diagnostic` field reports:

- `best_translation.dx/dy`: candidate shift relative to reference.
- `overlap_pixels` and `overlap_fraction`: the shared pixel area; a
  perfect match over a partial area is **not** full-frame parity.
- `different_pixels`, `different_ratio`, and
  `mean_absolute_channel_error` measured **inside the overlap**.
- `diagnostic_only: true`: the shift result has no effect on strict
  top-level `different_pixels`, `identical`, heatmap, or exit status.

The best offset minimizes overlap mismatch fraction, then channel error,
then absolute shift (preferring an unshifted image on ties). For a
featureless image the output may still be ambiguous: offset inference
is a **diagnostic hint**, not an authenticated camera-register measurement.

To bound CPU work, the shift finder accepts only input frames with
at most 512×256 pixels. Larger HD frames can still be compared normally,
but must be downsampled/cropped deliberately for shift diagnosis; never
automatically change the reference frame or parity threshold.

`tests/test_frame_translation_diagnostic.py` provides seven ROM-free
regression methods for signed translations, transparent edge exclusion,
ties, alpha suppression, invalid input bounds, single-pixel scenes
and a CLI demonstration where strict comparison still fails despite
perfectly aligned **partial** overlap. Local standalone testing of the
calculation passed, but the exact committed suite and native Switch
build remain blocked by Actions runner allocation (issue #20).

No original ROM, MAME capture or image asset is included.

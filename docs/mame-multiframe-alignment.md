# Stage 44 — multi-frame MAME register-offset diagnostics (dino)

## Problem

An isolated MAME CPS-A/CPS-B comparison at one frame number can give a
misleading sense of alignment: unchanged scroll registers often remain
byte-for-byte identical over several adjacent arcade frames.

`tools/mame_obj_sequence_alignment.py` investigates **a series of
frames** from the opt-in private MAME 0.289 C++ OBJ/video-update probe
(PR #26 / #27) and Lua frame_done reference recorder. It tests candidate
*index offsets* but does **not** assert that two hooks are synchronized.

## Requirements

A private directory containing at least four equally spaced capture
indices, each with all of:

- `frame-XXXXXXXX.manifest.json`: dino, frame_done, canonical frame index,
  the exact 384×224 geometry/size, big-endian raw words, incomplete OBJ
  provenance and five-file `file_crc32` schema introduced in PR #25.
- `frame-XXXXXXXX.cps-a-be.bin` (64 bytes) and
  `frame-XXXXXXXX.cps-b-be.bin` (64 bytes): Lua register captures,
  validated against the manifest's individual CRC32 values.
- `frame-XXXXXXXX.render-regs-be.bin` (128 bytes): C++ sidecar from
  `screen_update_cps1`, 32 CPS-A then 32 CPS-B 16-bit words.
- `frame-XXXXXXXX.buffered-obj-be.bin` (2048 bytes): C++ probed latched
  sprite state. Its size is checked but it is not interpreted by this tool.

Existing manifests lacking `file_crc32` will be rejected. Run the
checksum-aware private MAME Lua recorder from PR #25 to generate new
data; do not manufacture checksum entries.

## Private local workflow

The default source-probe/Lua interval has six nominal frames with a
two-frame interval: 900, 902, 904, 906, 908, 910.

```sh
python3 tools/mame_obj_sequence_alignment.py \
  /private/cps1-captures \
  --first-frame 900 \
  --frame-count 6 \
  --frame-step 2 \
  --max-offset-steps 2 \
  --out /private/local_outputs/mame-900-series.json
```

No ROM, raster pixels, sprite bytes or register contents are emitted:
only match counts, offset hypotheses, state counts and SHA-256 digests
of the source register sidecars. The output path uses exclusive creation,
so an existing report cannot be overwritten.

For an offset `k`, sample `i` of the C++ video-update register series
is compared to sample `i+k` of the Lua frame_done series. For example,
`offset_steps=+1` corresponds to **two nominal arcade frames** when
`--frame-step 2`, not necessarily two actual displayed frames.
Only samples present on *both sides* are compared; edge overlap size is
reported. Allowed offset steps: 0–4 and no greater than
`frame_count-3`, guaranteeing at least three pair comparisons.

A candidate's `exact_equal_fraction` is the count of identical
128-byte register sets divided by the number of pairs compared.
Ranking considers this fraction, then the number of matching pairs,
then minimal absolute offset. The tool reports all best-ratio
`ambiguous_best_offsets`, rather than hiding ties. Even a unique
best candidate is only marked `offset_hypothesis_informative: true`
when **both streams change**, at least three pairs match, and at least
two distinct matching register states are observed.

### Interpretation and safety

- `offset_hypothesis_informative: true` is **only** a useful investigative
  clue, *not* a proof of correct frame timing. Both streams could share
  stale or recurring states, and CRC32 is not authentication.
- Repeated/flat registers can give equal scores at several offsets.
  The tool then sets the informative flag to false and lists the tied
  candidate offsets (e.g. `[-2,-1,0,1,2]` for a static scene).
- The instrumented source and Lua collector must be run together with
  a common, private directory. Numeric label correspondence alone
  cannot determine MAME VBlank sprite-latch age or framebuffer timing.
- `frame_sync_verified` and `pixel_parity_eligible` are
  **unconditionally false** in every report. No native `scene.bin`
  promotion, original MAME parity certification, or Switch build occurs.
- The audit checks CRC32 of the **two** Lua register binaries, not the
  five entire components again. Use the separate importer in PR #25
  for full capture integrity.

## Verification boundary

Fifteen ROM-free unit tests were added covering aligned, one-step offset,
unchanged and recurring states, limited overlap, invalid frame count,
wrong 128-byte register size, same-length CRC damage, malformed manifests,
fake provenance, missing OBJ bytes and the fail-on-existing-output CLI.

This PR is stacked on #28; its *input format* additionally depends on
the separate capture-integrity chain #24 → #25. The GitHub Actions
runner-allocation issue #20 still prevents an authentic full checkout
test. The exact MAME 0.289 driver and original arcade game have not
been executed to validate timing; the first live captures remain pending.

No original game assets are included in this repository.

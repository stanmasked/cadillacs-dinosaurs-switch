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


## Stage 45 — never invent an exact offset without exact evidence

An issue in the original Stage 44 reporter was that **zero exact matches
at every offset** still resulted in a nominally selected
`best_offset_steps` (usually zero because of the overlap tie-break).
That numeric result was misleading even with an unverified sync flag.

The score now explicitly distinguishes two classes of evidence.

**Whole-register-set exact matches:** When no 128-byte render/Lua
register pairs match at *any* candidate offset,
`no_exact_register_pairs: true` and
`best_offset_steps`, `best_offset_nominal_frames`,
`best_overlap_pairs` are **null**, not a guessed zero shift.
When at least one pair matches, the original Stage 44 ranking and
its conservative `offset_hypothesis_informative` guard are unchanged.

**Weaker 16-bit word-distance diagnostic:** Each pair contains
64 16-bit CPS-A/B register words. New per-offset metrics are:

- `different_register_words`: number of unequal 16-bit words summed
  across actual overlapping pairs, without padding or wraparound.
- `compared_register_words`: exactly `64 × compared_pairs`.
- `register_word_mismatch_fraction`: unequal words divided by compared
  words; no individual CPS-A/B value or game data is emitted.
- `closest_word_offset_steps` and
  `closest_word_offset_nominal_frames`: a *unique* minimal word-error
  candidate only when **both** register streams vary and some words
  agree. Otherwise the offset is null.
- `closest_word_mismatch_fraction` and
  `ambiguous_closest_word_offsets`: the minimum fraction and all tied
  candidates. A static or repeating state sequence is not silently
  given a fabricated unique word-offset result.

This can identify an **approximate** one-sample shift even if every
overlapping pair has one changed register and therefore fails exact
equality. It is a diagnostic hypothesis, not an additional
`offset_hypothesis_informative` signal. The new
`word_distance_diagnostic_only: true` is unconditional.

Crucially, every report still has
`frame_sync_verified: false` and `pixel_parity_eligible: false`.
The observed best offset cannot be applied automatically to captured
VRAM, sprites or frames. Genuine original-game captures and a verified
MAME video timing build remain prerequisites for fidelity claims.

### Validation boundary

Eight new ROM-free regression test methods cover no-exact-result
handling, single-word mutations under one/two sample offsets, exact
pair behavior, repeated/constant states, word-count normalization and
explicitly unverified provenance. A faithful isolated Python
reproduction of the changed scoring function passed **8/8 new**
checks plus **7/7 previous scorer checks**. The full committed
regression module and repository-wide CI remain unverified because
GitHub Actions fails before runner assignment (issue #20). Neither
test run involved original game ROMs, live MAME, or Switch hardware.


## Stage 46 — register transition fingerprints (diagnostic only)

A secondary analysis, `tools/mame_obj_transition_evidence.py`,
compares **which of the 64 CPS-A/B 16-bit words changed between
consecutive sampled frames**, independently of whether all their values
match at either endpoint. It is invoked automatically by
`mame_obj_sequence_alignment.py` for the **same** locally captured
register sequences and bounded candidate offsets.

For each pair of adjacent frames, the tool computes a 64-bit change
mask internally. For offset `k`, it compares a render transition
`i→i+1` with Lua transition `i+k→i+k+1`.
A matching **nonzero** mask is counted; two unchanged transitions
are reported as `matching_inactive_transitions_non_evidence`, never as
supporting observations. Raw registers and change masks are **not**
included in the JSON output.

The new `transition_analysis` report contains one row per offset:
actual overlapping transition count, number and fraction of matching
*active* changes, count of distinct matching change patterns, and
inactive-match count. A transition offset is displayed only when its
match fraction is uniquely highest, at least **three active transitions**
match, and at least **two distinct nonzero change masks** match.
Flat or cyclic transition sequences with tied offsets produce a null
best offset and a list of ambiguous candidates.

`diagnostic_offset_metrics_agree` in the outer report is:
`true` or `false` when both the Stage 44/45 exact-register score
and the new transition-pattern score are independently *informative
under their own criteria*; otherwise `null`. **Both calculations are
derived from the same register captures**. Their agreement is NOT
independent hardware timing evidence, and disagreement is only a
reason to investigate the capture order, not proof of an error.

Even if matching change masks are uniquely ranked, the register
**values** may differ and another game frame may have undergone
the same pattern of writes. Therefore every report preserves
`transition_diagnostic_only:true`,
`frame_sync_verified:false` and `pixel_parity_eligible:false`.
The native Switch scene exporter is not bypassed.

### Verification

The exact GitHub-committed source for the transition helper
(Git blob `fc8a8a9f6822b5bf0e6db1480d9b05e7778e24c3`)
and ten-test module
(`b995cfb033f44ae3bfa4ab4f87d167162906e8c2`)
were reproduced byte-for-byte in a local Python environment; **all
10/10 tests passed**. These cover one-step shifts, aligned changes,
flat and recurring patterns, missing/change-poor evidence, wrong
buffer lengths, unrelated register changes, and non-wrapping edge
overlap. An additional CLI-regression assertion is committed to
the existing sequence test but not yet executed in the full repo.

CI and real MAME 0.289 sampling remain unverified due to the
pre-runner Actions failure ([issue #20](https://github.com/stanmasked/cadillacs-dinosaurs-switch/issues/20)).
No game ROMs, frame pixels, authentic OBJ buffers, native Switch builds
or actual gameplay captures are committed.

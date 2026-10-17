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


## Stage 47 — minimum real overlap for transition-offset hypotheses

Earlier Stage 46 required at least three matching active transitions
and two distinct change-mask patterns, but a candidate near the start
or end of a short capture could still be ranked informative using
**only three of the five transitions** from the default six frames.
Three matching transitions may look like a perfect `3/3` candidate
while discarding two entire transition observations.

The transition scorer now requires **at least 75% overlap** between
the two source transition series *before* returning an informative
offset. This is checked using exact integer arithmetic
`overlapping_transitions * 4 >= total_transitions * 3`; a nominal
frame outside the overlapping window is never padded or wrapped.
The threshold is deliberately conservative, not a physical
measurement of VBlank-latch timing.

New per-candidate fields:

- `overlap_fraction`: real overlapping transition pairs divided by
  all `frame_count-1` transitions in the source series.
- `overlap_sufficient`: whether that fraction meets 0.75.
- `transition_top_scoring_offset_steps`: leading candidate by the
  existing active-change score, **whether or not** overlap suffices;
  this field is only a troubleshooting clue.
- `transition_assessment`: one of
  `DIAGNOSTIC_HYPOTHESIS_ONLY`,
  `INSUFFICIENT_OVERLAP`,
  `INSUFFICIENT_ACTIVE_CHANGE_EVIDENCE`, or
  `TIED_BEST_CANDIDATES`. A reason is provided even when the actual
  best offset is null.
- `transition_minimum_overlap_fraction`: currently `0.75`.

Examples: with six sampled frames, the series contains five
transitions. An offset of **two sample steps** matches at most
`3/5=0.60`, so its `transition_best_offset_steps` is now
`null`, even if all three transition masks agree. An offset of
**one step** can cover `4/5=0.80` and remains eligible *for a
diagnostic hypothesis* if the other diversity/uniqueness conditions
hold. With ten sampled frames, a two-step shift covers `7/9≈0.78`
and can also qualify. In every case, one must still inspect actual
MAME timing, and both `frame_sync_verified` and
`pixel_parity_eligible` stay **false**.

### Exact source regression

The updated `tools/mame_obj_transition_evidence.py` and
`tests/test_mame_obj_transition_evidence.py` were copied
**byte-for-byte** from this GitHub branch into an isolated Python test
directory. Their local Git blob SHA-1 values were verified against
GitHub: `e3a2f56a1dcc3eb7e2f2fa8c4fafa9726fa1fe44` and
`52161c628337d96049473e0e393734542a658da2`.

The **15/15 committed unittest methods passed** using
`python -m unittest discover -s tests -p
test_mame_obj_transition_evidence.py -v`, covering all original
transition cases and five new edge-coverage regressions.

This does not establish a full-repository test pass, successful
MAME-native compile, real dino captures, original framebuffer parity,
or Nintendo Switch hardware verification. GitHub Actions currently
fails with `runner_id=0`, `steps=[]` before any tests can run
(issue #20). No original game files or gameplay captures are committed.


## Stage 48 — leave-one-transition-out stability of frame-offset clues

The transition analysis can now be inspected for sensitivity to a
single coincidental register change, independently of the usual
`>=75%` real-overlap requirement.

The new `tools/mame_obj_transition_stability.py` implements a
**bounded leave-one-transition-out (LOO) diagnostic**. For each of
the `frame_count - 1` render transition *indices*, it omits that
**one comparison observation** from every candidate offset, then
re-scores all candidate shifts without reordering frames, stretching
the time axis, wrapping indices or creating synthetic transitions.

LOO evaluation is skipped if the Stage 47 base analysis did not have
an informative transition-mask hypothesis. A candidate only survives
an omitted observation if it is still the **uniquely highest-scoring**
shift at the *same offset*, has at least three matching active
transitions and two distinct matching nonzero change masks, and
still covers at least 75% of the remaining render observations.

The existing `mame_obj_sequence_alignment.py` CLI now includes an
additional `transition_stability` object:

- `leave_one_out_applicable`: whether the original transition
  scorer yielded an informative diagnostic offset.
- `leave_one_out_trial_count`: number of omitted-index trials.
- `leave_one_out_consistent_trials`: how many reruns preserved the
  same candidate with adequate evidence.
- `leave_one_out_unstable_indices`: **render transition indices**
  (zero-based) whose omission broke that diagnostic hypothesis.
- `leave_one_out_stable`: true only if **every** omission preserved
  that offset under the same diversity and overlap guards.
- `leave_one_out_reason`: explicit
  `BASE_HYPOTHESIS_INCONCLUSIVE`,
  `SENSITIVE_TO_OMITTED_TRANSITIONS` or
  `ALL_OMISSIONS_PRESERVE_DIAGNOSTIC_OFFSET`.

For example, with six frame samples and an otherwise unambiguous
one-step shift, **four matching transitions** can remain convincing
when any single comparison is omitted. A nominally best shift relying
on only **three** matched transitions often falls below that
minimum as soon as one of those observations is removed. Flat,
periodic or low-coverage input is rejected *before* LOO scoring.

This method omits one *comparison* at a fixed render transition
index, **not an arcade frame**; removing a frame and joining its
neighbors would create a nonexistent two-frame transition. The
LOO metric intentionally does not do that.

**Limitation:** all leave-one-out trials reuse the *same* CPS-A/B
register captures and are mathematically correlated. Stability
does not prove MAME callback order, VBlank sprite age, physical
raster timing, originality of captured data or screenshot pixel
parity. As with all other diagnostics,
`leave_one_out_diagnostic_only:true`,
`frame_sync_verified:false` and
`pixel_parity_eligible:false` are unconditional. No automatic
offset correction is applied to graphics RAM or OBJ.

**Validation:** the source module and eight new unit tests were
independently saved as byte-for-byte Git-matching local files,
and the original 15 Stage 47 tests and eight new LOO tests passed
(**23/23**). A further **1,188 bounded randomized synthetic
series** of four to 24 frames checked index bounds, absence of
runtime failures, per-trial accounting and that LOO never promotes
an inconclusive base result. These synthetic tests do not replace
a full GitHub Actions run or actual MAME 0.289 gameplay capture.
The GitHub runner allocation issue remains open as issue #20.


## Stage 49 — conservative cross-method diagnostic verdict

The multi-frame CLI now includes a `diagnostic_verdict` object generated
by `tools/mame_obj_diagnostic_verdict.py`. It reconciles three **correlated**
observations drawn from the **same CPS-A/B capture**:

1. A uniquely informative exact **128-byte register-state offset**
   (Stage 44/45, `offset_hypothesis_informative`).
2. A uniquely informative **changed-register transition-mask offset**
   with >=75% real transition overlap (Stage 46/47).
3. A **leave-one-transition-out** result in which the candidate survives
   every omission with unchanged offset and adequate active evidence
   (Stage 48).

The verdict is **fail-closed** on inconsistent input: required flags must
be genuine booleans, neither source may assert pixel parity or frame
synchronization, informative offsets must be bounded integers, and LOO
trial counters/unstable indices must be complete, consistent and
non-duplicated. It rejects malformed metadata instead of manufacturing
a stronger conclusion.

The report's `status` is exactly one of:

- `CONSISTENT_BUT_UNVERIFIED`: exact and transition hypotheses agree,
  **and** the full LOO check is stable. Only this case supplies a
  `diagnostic_candidate_offset_steps` number.
- `CONFLICTING_REGISTER_DIAGNOSTICS`: the two informative scores favor
  different offsets; candidate remains null even with stable LOO.
- `FRAGILE_REGISTER_DIAGNOSTIC`: the two offsets agree but at least
  one LOO trial broke the changed-register hypothesis.
- `EXACT_ONLY_UNCORROBORATED`: exact-value score is informative but
  changed-register transitions are not.
- `TRANSITION_ONLY_UNCORROBORATED`: changed-register score is
  informative but full 128-byte register comparison is not.
- `INSUFFICIENT_REGISTER_EVIDENCE`: neither score is informative.

The exact, transition and LOO checks are **not three independent
measurements**: every result is computed from the same captured bytes.
The verdict therefore records
`independent_physical_measurement_count:0`,
`diagnostic_only:true`, `frame_sync_verified:false`, and
`pixel_parity_eligible:false` **in every case**, including
`CONSISTENT_BUT_UNVERIFIED`. It neither modifies the native
Switch scene exporter's guard nor corrects offsets automatically.

The metadata-only CLI still uses the prior Stage 44 defaults:

```sh
python3 tools/mame_obj_sequence_alignment.py \
  /private/cps1-captures --first-frame 900 --frame-count 6 \
  --frame-step 2 --max-offset-steps 2 \
  --out /private/local_outputs/mame-900-stage49.json
```

Original CPS-1/ROM data, register arrays, sprites and screenshots never
enter the JSON report. Current status is preparation for real MAME 0.289
verification, not a verified frame capture or playable Switch port.

### Validation and CI boundary

The **exact GitHub-committed** Stage 49 classifier source and its new
test module were checked using Git blob SHA-1 and executed locally:
**13 new tests passed**; the 23 Stage 47/48 transition and stability
tests also passed, totaling **36/36** on a ROM-free focused local tree.
The test cases include disagreements, fragile matches, false
pixel-parity declarations, invalid types and mismatched LOO counts.
An existing multi-frame CLI regression now checks the new verdict
object; that broader CLI integration check was committed but has not
yet run in a full clean repository checkout.

GitHub Actions remains blocked before runner allocation as tracked in
[issue #20](https://github.com/stanmasked/cadillacs-dinosaurs-switch/issues/20).
A real compiled MAME 0.289 probe and original game's framebuffer timing
remain prerequisites for fidelity claims. No original ROMs, private
captures, licensed sprites, commercial source or authentic game frames
are committed.


## Stage 50 — cross-check the input reports before trusting their consistency

The Stage 49 diagnostic verdict now checks that the three register-only
observations actually refer to **compatible sampled frame series**, rather
than accepting their summary booleans at face value.

For a full Stage 49 CLI report, `tools/mame_obj_diagnostic_verdict.py`
validates the following before it may emit
`CONSISTENT_BUT_UNVERIFIED`:

- The source's `sample_count` is an integer from 4 to 24 and
  `frame_step` is an integer from 1 to 120. A boolean or a lone
  incomplete field is refused.
- An applicable leave-one-out assessment contains exactly
  `sample_count - 1` transition-omission trials.
- Every informative offset uses **consistent nominal frame units**:
  `best_offset_nominal_frames` and
  `transition_best_offset_nominal_frames` must equal the corresponding
  sample-step offset times `frame_step`.
- The claimed exact-offset candidate, if candidate rows are present,
  must actually contain **at least 3 fully matching register frames**
  and **2 distinct matching states**.
- The transition candidate, if candidate rows are present, must have
  sufficient real overlap, at least **3 active matching transitions**
  and **2 distinct matching change-mask patterns**.
- The LOO reason must agree with its actual flags and counter results:
  inconclusive, all omissions pass, or sensitive to omitted transitions.

Malformed or contradictory complete reports are **rejected** instead
of being relabeled with a favorable status. Older callers passing only
three minimal diagnostic dictionaries remain supported; they **do not**
receive extra source-provenance validation merely by omitting metadata.
This is a consistency check, **not cryptographic authentication** of
actual MAME data, real-time callback alignment, or original sprites.

**Execution evidence:** The exact GitHub-committed updated classifier
(Git blob `5132f06a40b246ad5f074281337144a569512a95`) and nine-test
cross-report regression module
(`b55b515e9a97b9f88991e03ee33d44dddf1cdfe2`)
were verified against local Git blob hashes. With the existing
Stage 47–49 modules, **45 of 45 ROM-free local unittest methods
passed**. The additional tests use *actual returned report objects*
from `transition_diagnostic()` and `transition_leave_one_out()`,
not only manually invented dictionaries.

This validation does **not** constitute a full clean repository
checkout, real MAME 0.289 gameplay capture, native Nintendo Switch
render test, or successful GitHub Actions run. The existing CI
runner-allocation blocker remains in issue #20. The report still
unconditionally has `frame_sync_verified:false` and
`pixel_parity_eligible:false`.

## Stage 51 — actual end-to-end local CLI execution on synthetic private captures

Unlike the earlier focused helper tests, the **unmodified production
`tools/mame_obj_sequence_alignment.py` from PR #34** was reconstructed
byte-for-byte in the local test workspace and verified against Git blob
`8c94251b4af8cfd84ca1df028e00276335552f5d`.

The new `tests/test_mame_obj_cli_end_to_end.py` writes temporary
**synthetic**, valid-shaped six- or ten-frame capture files with canonical
`frame-XXXXXXXX` names, five-entry CRC32 manifests, 64-byte Lua CPS-A,
64-byte Lua CPS-B, 128-byte C++ register sidecars and 2048-byte buffered
OBJ files. Then it invokes the **real production CLI `main()`**
without mocking the filesystem, capture loader, scorer, transition
diagnostic, LOO checker, verdict classifier, or JSON writer.

Fourteen new end-to-end regression methods cover:

- Correctly aligned dynamic registers → conservative
  `CONSISTENT_BUT_UNVERIFIED` with zero nominal offset;
- One-step synthetic capture lag → the same *unverified* classification
  with offset +1; a short two-step lag does **not** receive independent
  transition support because only 3/5 transitions overlap;
- A ten-sample two-step lag can pass the 75% overlap and LOO guards,
  while a static scene, or periodic changed-register masks, remain
  explicitly inconclusive / uncorroborated;
- CRC32 corruption **without changing input size**, truncated OBJ,
  wrong frame-number metadata, missing checksum manifest, and absent
  C++ probe all produce an error exit and **no JSON output**;
- Existing output is preserved byte-for-byte, unbounded frame counts
  are rejected, and a valid JSON report contains only diagnostic counts,
  SHA256 and status fields, never raw CPS register or OBJ word arrays.

**Reproducible local execution:** The new test module was copied
byte-for-byte from the committed GitHub file, verified against Git
blob `bc004d781ce9679125334d361132bec53dc6d9f2`, and run
alongside the prior 45 unit tests. The actual production CLI module,
new test file, and Stage 47–50 helper sources were verified against
their corresponding remote Git blobs.

```sh
PYTHONPATH=. python -m unittest discover -s tests -v
# 59 tests, OK (45 earlier + 14 end-to-end CLI)
```

**Precise boundary:** This confirms that the assembled production
*Python diagnostic path* works on fabricated capture artifacts under
local Python, including its file I/O and JSON. It does **not** exercise
actual MAME 0.289 video callbacks, original `dino` ROMs, authentic
VBlank-latched OBJ timing, raster/pixel comparison, complete repo
tests/CI or a Switch NRO build. All `frame_sync_verified` and
`pixel_parity_eligible` values remain false even when the synthetic
register sequence has a unique best offset. No generated capture files,
ROMs or original arcade assets are committed.

GitHub Actions runner allocation remains tracked in issue #20.

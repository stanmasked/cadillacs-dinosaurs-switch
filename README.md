# Cadillacs and Dinosaurs — Nintendo Switch HD Remake

Target: **Capcom CPS-1, World 930201, MAME dino**.

## Current status
**ROM-free training-room prototype and CPS-1 diagnostic viewer.** The NRO
contains a newly authored, playable placeholder movement/jump/attack sandbox
that requires **no original game graphics**. It also retains user-local
tile/scene/sequence viewers when personal CPS-1 graphics are supplied.
**This is not the original Cadillacs and Dinosaurs game or a playable
game-faithful remake.** There is no original character/level gameplay,
emulated original AI, original audio or real Switch hardware runtime proof.
No commercial assets are stored in the public repository.

See [training-room controls, invented effects and limitations](docs/switch-rom-free-training-room.md).
The technical build now includes entirely original, synthesised PCM cues (no
sample archives or licensed soundtrack), a bounded libnx audio output backend,
and a **host-only WAV preview**:

```sh
python3 tools/dino_sfx_preview.py --out /your/private/folder/dino-training-effects.wav
```

Actual speaker/headphone output on a physical Switch remains unverified;
audio hardware failures leave the technical prototype playable without sound.

To **actually play and inspect the portable C mechanics on a desktop**,
run `python3 tools/dino_host_preview.py` with Python, GCC and Tkinter.
No ROM or Switch emulator is required. The headless mode
(`--headless --ticks 180`) runs actual C combat and synthetic audio
and optionally writes a no-overwrite PPM frame; this is not
Switch hardware or GPU emulation. See
[desktop gameplay preview and CI artifact](docs/host-native-gameplay-smoke.md).

For ROM-free testing in an installed Nintendo Switch emulator, follow
[the emulator launch and manual smoke-test guide](docs/switch-emulator-smoke.md).
The NRO now includes a **180-tick built-in demo**: enter the ROM-free
training room, press **Minus (-)**, and inspect the frozen final frame
(`C REPLAY 180/180 DONE`, player HP 4, three confirmed hits). **Y**
resets. The input trace comes from the *same C module* exercised
by the desktop gameplay tests, eliminating divergent host/console
scripts. This is preparation for testing in a real Switch emulator;
it is not proof that one has been run.
The emulator guide includes NRO format and SHA-256 verification,
a bounded launcher probe and controller/visual/audio review steps. A launch probe reports **only
process survival**, never a false emulator gameplay pass.

## Build
Install [devkitPro switch-dev](https://www.switchbrew.org/wiki/Setting_up_Development_Environment),
export DEVKITPRO, then run `make`. Expected result:
`cadillacs-dinosaurs-switch.nro`. ROM-free native Switch builds have
passed GitHub Actions; a physical Switch gameplay test has not been
confirmed. Without `gfx.bin` the technical sandbox opens automatically.

## ROM audit
Run `python3 tools/verify_rom.py /path/to/your/dino.zip` using your own legitimately acquired files. Never commit ROM data.

## Milestones
1. Audit original CPS-1 ROMs and establish gameplay references.
2. Create a deterministic gameplay-faithful runtime baseline.
3. Implement Switch video, audio and local controllers.
4. Restore HD sprites, stages, interface and effects.
5. Test co-op, performance, levels and original input timing.

## Intellectual property
Cadillacs and Dinosaurs belongs to its respective owners. Distribution of original assets or a public IP-based remake requires appropriate rights.
## Graphics research (work in progress)

The CPS-1 4bpp decoder supports `8x8-left`, `8x8-right`, `16x16`, and `32x32`.
Generate **local-only** diagnostic tile sheets from your own parent `dino.zip`:

```sh
python3 -m unittest discover -s tests -v
python3 tools/cps1_tiles.py /path/to/dino.zip --layout 16x16 --start 0 --count 128 --columns 16 --scale 2 --out local_outputs/tiles16.png
```

Generated images use grayscale placeholders for 4bpp pixel indices; they are not authentic game colors. Correct palette selection requires runtime palette RAM. See [tile decoder technical notes](docs/cps1-tile-decoder.md). The test suite uses synthetic ROM fixtures and **does not require or fetch commercial game data**.

## CPS-1 palette and tile bank research

World 930201 uses MAME's `CPS_B_21_QS2` and `CD63B` video configuration. The project now contains:

- `tools/cps1_video.py` — exact CPS-1 16-bit palette-color formula, six-page palette-copy control, CD63B tile bank mapping and composite sprite-code expansion.
- `tools/cps1_color_atlas.py` — creates a **local-only** color PNG from user-owned `dino.zip` plus a **runtime gfx RAM palette snapshot**. The ROM alone does not contain sufficient data to infer the palette active during gameplay.
- `tests/test_cps1_video.py` — synthetic unit tests for palette, graphics mapping, sprites and PNG output.

Full commands, input format and limitations: [CPS-1 video/palette research](docs/cps1-video-palette.md).

```sh
python3 -m unittest discover -s tests -v
python3 tools/cps1_color_atlas.py /private/dino.zip /private/palette_snapshot.json \
  --layer sprites --color 0 --count 32 --out local_outputs/sprites_color.png
```

**Verified locally:** 34/34 Python tests on Python 3.13; graphics mapping and color atlas export also exercised with the user-provided parent ROM and deliberately artificial palette. **Not yet verified:** GitHub Actions run, playable native Switch build, authentic RAM-derived palette, gameplay rendering.


## Frame composition from captured CPS-1 video RAM

`tools/cps1_frame.py` is now a **partial offline compositor** for `dino`:
three 64×64 tilemap RAM scanners, CPS-B layer order, palette/color groups,
already-buffered OBJ sprite RAM, block-sprite flips, and the hardware
384×224 visible viewport. It does not capture memory from an emulator
itself and is **not pixel-perfect** (priority masks, line scrolling,
flipscreen and several other effects remain unimplemented).

To replay an actual game frame you must supply a **local runtime RAM
snapshot** along with your own ROM. There are no real game-state
snapshots in the repository. See [snapshot schema and known limitations](docs/cps1-frame-compositor.md).

```sh
python3 -m unittest discover -s tests -v
python3 tools/cps1_frame.py /private/dino.zip /private/frame_snapshot.json \
  --out local_outputs/partial_frame.png
```

Validation: **50/50 Python tests passed locally**. The renderer also
produced a 384×224 PNG using real ROM pixel data with **synthetic test
VRAM and synthetic palette**, which is *not a game screenshot*.
Nintendo Switch compilation and GitHub Actions execution remain unverified.

## QS2 frame replay — raster / priority / capture conversion

A local raw-dump adapter `tools/cps1_capture.py` converts **coherent MAME/CPS-1 RAM and register dumps** into the replay JSON. It requires 0x40000 bytes of graphics RAM, 0x40 bytes each of CPS-A/CPS-B registers, and 0x800 bytes of **buffered** sprite OBJ RAM; the original `dino.zip` is only needed for the subsequent private frame rendering step. Native-game RAM capture is not yet automated.

The frame renderer now accepts `priority_masks`, `video_control`, `rowscroll`, and `rowscroll_offset` to model CD63B sprite occlusion and per-scanline Scroll2 scrolling. A separate effective palette RAM capture is necessary for *authentic* colors; otherwise the adapter explicitly labels the current source-palette estimate as approximate.

See [raw capture workflow and exact register mappings](docs/cps1-capture-and-raster.md).

Local validation: **68/68 Python tests passed** and a 384×224 diagnostic frame was reconstructed from *synthetic* raw RAM dumps plus the locally supplied real `dino.zip` graphics. The resulting scene is not an original gameplay frame.

A dedicated [Switch native bootstrap workflow](.github/workflows/switch-bootstrap.yml) now attempts a **ROM-free** `.nro` build in the official devkitPro devkitA64 container. Its CI outcome and real-console runtime remain unverified.

## Verified Switch NRO bootstrap and frame parity QA (2026-10-16)

The `Makefile` follows the canonical devkitPro/libnx application layout.
The private-repo pull-request CI executed in `devkitpro/devkita64:20260219`
and **successfully built and uploaded a valid native Switch NRO**:

- [NRO build run #38929163586](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/38929163586) — SUCCESS, artifact `cadillacs-dinosaurs-switch-bootstrap`. Verified `NRO0` header at offset `0x10`, file size **166,085 bytes**, SHA-256 `ef682e60afb7f1d7ba79b04b2368e5239926d330e65f2cca4eec3fbdefd47093`.
- [Python test run #38929164566](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/38929164566) — SUCCESS, **77 tests** including nine new reference-frame comparator tests.

`tools/frame_compare.py` reads two same-size RGBA PNG frames, counts
pixel/color differences, and optionally saves a red-channel error heatmap.
Usage and capture requirements: [Pixel-exact frame QA](docs/frame-parity-testing.md).

```sh
python3 tools/frame_compare.py /private/mame_reference.png \
  /private/cps1_reconstruction.png \
  --diff local_outputs/pixel_error.png
```

**Important:** The NRO is a ROM-free **technical bootstrap**, not yet a playable
game. Native compilation and output format are confirmed; real Switch hardware
boot and gameplay functionality are not tested. A real MAME reference frame
has not been captured, so there is no pixel-parity claim for the actual game.

## Native Nintendo Switch graphics inspector — v0.2

The ROM-free NRO now renders a **native 1280×720 interactive grid** of
actual CPS-1 16×16 graphics tiles when a local, user-provided `gfx.bin`
is available on SD. These are grayscale palette-index previews, **not**
restored HD images, gameplay, or authentic in-game colors. If the asset
is missing, the app explains the required path and exits with PLUS.

```sh
# On a computer: assemble a 4 MiB region from your own parent ROM set
python3 tools/cps1_gfx.py /private/dino.zip --out-local gfx.bin

# On Switch SD card: place the binary at
# sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin

# ROM-free local regression tests
python3 -m unittest discover -s tests -v
gcc -std=c11 -O2 -Wall -Wextra -Werror -Isource \
 tests/cps1_tile_native_test.c source/cps1_tile.c -o /tmp/cps1_tile_tests
/tmp/cps1_tile_tests
```

Detailed installation, navigation and limitations: [Switch tile inspector](docs/switch-tile-inspector.md).

**Never commit gfx.bin, game ROMs or derived copyrighted assets.**

## Nintendo Switch v0.3 — native partial scene replay

Switch now has a **native C frame compositor** (not just a tile-sheet viewer).
It optionally reads a local `scene.bin` snapshot alongside the owner's
`gfx.bin`, reconstructs three CPS-1 background layers, sprites, effective
palette RGB, QS2 priority pens and Scroll2 scanline scrolling into a
**384×224** static scene, and presents it at **3× nearest-neighbor scale**
on the Switch framebuffer. Press **X** to toggle the scene; existing
tile browsing still works without a snapshot.

The compact binary scene format uses magic `CPS1SCN1`, a strict size
and CRC32; its exporter requires **effective runtime palette RAM**, not
a guessed ROM palette. Details: [installation and capture format](docs/switch-native-scene-v03.md).

```sh
python3 tools/cps1_scene_export.py /private/frame_snapshot.json --out scene.bin
# SD: switch/cadillacs-dinosaurs-switch/gfx.bin
# SD: switch/cadillacs-dinosaurs-switch/scene.bin
```

No ROM or private RAM capture is uploaded to GitHub. Synthetic automated
tests compare native C-composed pixels to the Python reference. This is
**static frame replay, not interactive gameplay, HD-restored graphics, or
confirmed pixel parity with a real MAME frame**.

## Native Switch v0.4 — interactive scene camera

The local-only scene inspector supports manual **on-device camera panning**
of three background tilemaps. In scene mode press D-pad to scroll, hold ZR
to pan faster, press A to reset to the original captured scroll values, and
press X to return to tile browsing. Backgrounds are re-rendered natively
from 4-bit CPS-1 graphics; sprite coordinates and palette state remain
those of the captured frame.

The `scene.bin` format and required local `gfx.bin` are **unchanged**.
No additional commercial assets are included in the ROM-free NRO.
Details and limitations: [Interactive scene inspection v0.4](docs/switch-interactive-scene-v04.md).

This is a developer camera test, **not movement/gameplay of characters**.
CI exercises native-vs-Python pixel equality, 16-bit wrap and scroll reset;
real console testing and synchronized MAME frame capture remain pending.

## Nintendo Switch v0.5: native frame sequence player

An optional private `sequence.bin` now provides a **bounded 1–120-frame
timeline** of existing `CPS1SCN1` snapshots. The native C renderer plays
back the sequence using a real timer with a 60 Hz virtual tick clock,
rather than incorrectly assuming that one display iteration is one
game frame. It supports pause, previous/next frame, and 0.5×/1×/2× speed.

```sh
# Purely synthetic, ROM-free animation test from generated state snapshots:
python3 tools/cps1_sequence_export.py --demo --fps 12 --out sequence.bin

# Alternatively, pack your own *synchronized* authorized CPS-1 capture JSONs:
python3 tools/cps1_sequence_export.py \
    --frames-dir /private/captured-frames --fps 12 --out sequence.bin
```

Copy sequence.bin next to your privately created gfx.bin on Switch SD.
If sequence.bin is unavailable or invalid, v0.4's optional static
scene.bin and tile inspector remain available. See
[full installation, format, controls, and limitations](docs/switch-sequence-v05.md).

**This is diagnostic motion of independent static captures, not original
game execution, character animation restoration, or real-time gameplay.**
No commercial assets are embedded in the GitHub build.

## Experimental MAME reference capture — live-data bridge

The next graphics-fidelity milestone is **authentic CPS-1 reference pixels**,
not another synthetic demonstration. Added:

- `tools/mame_cps1_capture.lua`: runs through MAME's documented
  `-autoboot_script` interface and samples real **384×224 RGB frames**,
  effective 3072-color palette, CPS-A/B registers, and the QSound board's
  **0x30000-byte** mapped graphics RAM. The Lua script has not yet been
  tested in a running MAME session.
- `tools/mame_capture_import.py`: validates lengths/endian/map boundaries
  and converts native MAME RGB bytes into a lossless reference PNG and
  **explicitly partial** register/VRAM snapshot.
- A safety guard in `tools/cps1_scene_export.py` blocks promoting partial
  captures to native Switch `scene.bin` without VBlank-latched OBJ.

See [MAME reference capture instructions and limitations](docs/mame-live-reference-capture.md).

```sh
mkdir -p cps1-captures
mame dino -rompath /private/mame-roms \
    -autoboot_script /path/to/tools/mame_cps1_capture.lua
python3 tools/mame_capture_import.py cps1-captures frame-00000900 \
    --out-dir local_outputs/mame-reference
```

**Important:** Real captured MAME frames do not yet exist in this
repository or test environment. The Lua capture cannot access the
driver's VBlank-latched sprite buffer; incomplete replays are not
pixel-parity eligible. Original data and derived frames stay local.

## Stage 162 — preserve per-window A/B skip direction, not just aggregate totals

The experimental NeXium audout A/B report now exposes six separately labelled 150-tick differences in later-batch audio skips **only** when both independent guests have matching coarse single/first/later exposure in every window. It also counts windows with fewer vs. more skips and explicitly flags opposing directions. A net-zero aggregate is not presented as absence of local regressions. Any coarse exposure mismatch nulls all these new difference and direction fields. Even matched windows cannot authenticate exact frame pacing, host timing, causal benefit, or physical Switch sound; those verification fields stay false. Four ROM-free regressions cover uniformly fewer skips, mixed directions hidden by a zero aggregate, unchanged windows and invalid cross-run matching. The normal audio synthesizer, audout queue and guest NRO runtime are unchanged.

## Stage 163 — detect cross-window cancellation of batched audout page returns

The experimental A/B diagnostic now carries a per-150-tick count of *later-batch* page returns alongside the existing per-window skip data. Under matching coarse exposure only, it publishes six signed page-return deltas, counts intervals with increased/decreased returns and flags opposite directions that would otherwise cancel to a zero total. A mismatch in the single/first/later tick exposure nulls every new page-return comparison. The metadata helper checks the six return windows, their canonical boundaries, nonnegative integer counts and reconciliation to the validated 900-tick later-page-return total. The full guest ledger verifier remains the mandatory production acceptance gate; the descriptive helper alone does not certify guest provenance or timing. Four additional ROM-free regression methods cover unchanged returns, cross-window cancellation, unmatched exposure and forged page-return windows. No causal improvement, physical-device sound, host-timing equality or original arcade audio is claimed. No ROM, raw PCM, native audio driver, queue policy or cover file is changed.

## Stage 164 — avoid skip comparisons confounded by different page-return distributions

The 900-tick NeXium experimental audout A/B report now distinguishes matched *render exposure* from matched *render exposure plus observed later-batch page-return counts in each of six 150-tick windows*. It retains the previous descriptive skip and page-return deltas, but publishes the newly stricter `matched_exposure_and_returns_later_skip_count_delta` and per-window counterparts **only** if both coarse tick exposure and all six return counts match. If any window reallocates returns (even with equal grand totals), the stricter deltas are null and a descriptive return-shift-confounding flag is set. With mismatched exposure the status of return matching itself remains unknown/null, rather than falsely reporting a validated mismatch. The result is still noncausal: identical coarse counts cannot establish identical host scheduling, release timestamps, independent guest authentication, real Switch output or lower audio latency. Four new ROM-free fixture tests cover matching returns, cancelling inter-window shifts, differing exposures and one additional page return. Malformed report keys are handled as a structured fail-closed CLI error. No game data, production sound driver, audio-queue policy or cover files are modified.

## Stage 165 — guard audio skip comparisons against *all* release-position shifts

Even when the two A/B runs have matching six-window single/first/later tick exposures and identical *later-batch* return counts, their shared two-page audout queue can behave differently if pages were released during a single-tick frame or the first tick of a batch. The ROM-free descriptive verifier now validates per-window returns for all three positions (single-frame, first-batch and later-batch), with exact 900-tick totals reconciled against the existing guest report. It exposes six position-wise differences and the separate `matched_exposure_all_position_return_counts_matched` diagnostic. The stricter, previously named `matched_exposure_and_returns_later_skip_*` deltas are now emitted **only** when the exposures and **all three** page-return position counts match in each window. The earlier later-only matching fields retain their precise previous meaning for compatibility, but cannot by themselves authorize strict skip comparisons. If the coarse tick exposure differs, all cross-run position comparisons remain null. Five new ROM-free test cases cover equal schedules, within-window single/first redistribution, across-window redistribution with equal totals, malformed or inconsistent counts, and exposure mismatch.

These are *per-150-tick aggregate controls*, not evidence of equal per-call timings, same host load, causal benefits, real hardware audibility or reduced audio latency. The production guest's independent full-ledger validation remains mandatory. No original game content, audio driver, queue policy, console build source or approved artwork is altered.

## Stage 166 — reject misaligned audio exposure ledgers even in the standalone helper

The ROM-free A/B exposure helper now checks the canonical integer start/end of **all three** per-150-tick sources: the batch-position, render-mode and release-position windows. It no longer assumes that same-index records refer to the same interval. Every window must also reconcile batch-position first/later steps with the independent mode batch-step count, reconcile first/later skipped admissions with the mode batch-skip count, and keep single-tick skips within single-tick exposure. Noncanonical booleans, floating-point boundaries and contradictory counts fail closed. Four new synthetic tests exercise forged mode timing, inconsistent mode counters, noncanonical boundaries in all three sources and an untouched passing fixture.

This is defense in depth for the helper; the production A/B comparator still executes its original full guest-ledger verifier before any comparison. The unchanged 900-tick statistics remain *descriptive*: neither equal aggregate exposures nor matching per-position page-return counts prove identical audio event ordering, host load, hardware sound or improved latency. No game ROMs, raw audio, queue policy, core gameplay or approved cover art are changed.

## Stage 167 — reconcile 150-tick exposure windows with the 900-tick audio summary

The ROM-free A/B exposure helper now independently checks that the six validated 150-tick windows exactly sum to the nine relevant global counts: single-frame steps, first/later batch steps, single-frame skips, first/later batch skips, total batched steps, total batched skips and total simulation ticks. This supplements the earlier window-local mode/position/release consistency checks: an internally plausible redistribution in one window must not quietly contradict the global counters. The diagnostic profile also exposes per-window `single_skips` for the existing conservation audit. Four additional synthetic regression methods verify complete reconciliation, reject altered aggregate counters and catch compensated first/later step or skip reallocation. The production A/B path still first invokes the independent full guest report verifier, so these checks are defense in depth.

Confirmed from GitHub Actions on the previous stage-166 head: the public ROM-free privacy gate completed successfully, while Python, Switch, NeXium and native-preview workflows had not finished at last check. No emulator performance or audio-quality improvement is claimed. No ROM, private trace, raw PCM, queue policy, game engine or approved packaging art is changed.

## Stage 168 — repair synthetic A/B drift fixtures after conservation hardening

The standalone A/B helper now enforces window-to-global 900-tick conservation (stages 166–167), which revealed a test-harness regression: several older *helper-only* negative/control scenarios moved two batched ticks into single-tick exposure but did not adjust the independent window-mode and 900-tick counters. They could fail with a ledger-consistency error before exercising the intended `per_150tick_batch_exposure_matched = false` behavior. Tests now use one ROM-free `repartition_one_batch_frame_as_two_singles()` fixture builder, consistently updating batch-position windows, corresponding render-mode windows, aggregate first/later/single step counts and batch frame count. The cross-window zero-net skip scenario now balances first-vs-later skip positions inside both modified windows, preserving batch skip and global skip totals instead of fabricating a malformed mode ledger. Two direct regression tests assert the repartitioned metadata still passes the standalone conservation validator and yields **null** cross-run comparators when coarse exposure differs. Deliberately malformed scenarios continue to fail closed.

These are synthetic arithmetic fixtures, not real guest run evidence or proof of identical frame pacing. The full GitHub test suite and NeXium execution must still pass before accepting the branch. Only ROM-free tests/documentation changed; audio runtime, original ROM, raw PCM and artwork are untouched.

## Stage 169 — reconcile skipped admissions against independent checkpoint witnesses

The ROM-free audout A/B exposure helper now cross-checks all six 150-tick skipped-admission totals against two independently recorded witnesses: the render-mode window's `full_queue_skips` and the checkpoint-delta array. The single-frame plus first/later batch skips must equal both numbers for each interval. Across the full 900 ticks, the sum must also equal `full_queue_skips` and `audout_blocks_skipped`. Missing, noninteger, negative or contradictory checkpoint counts fail closed before the descriptive A/B comparison can run. Five synthetic regression tests cover valid reconciliation, malformed checkpoint windows, falsified global totals, forged mode skips and a legal zero-net first/later redistribution.

This check is defense in depth: the normal A/B command already invokes the independent full NeXium guest ledger verifier. It does not authenticate game execution, equal wall-clock scheduling, causal sound improvements or physical-device latency. The previous Python/NeXium CI runs were still queued when checked; this stage is not declared CI-passed. No original game data, guest audio runtime, buffer policy or approved cover is modified.

## Stage 173 — distinguish lifetime audio diagnostics from per-open PCM state

Python CI for the earlier head `b322b3e5` identified two failing release-versus-selftest adapter comparisons, both caused by comparing the library's lifetime `simulated_ticks` and `audio_errors` counters as if they reset on every sound open. Stage 172's `2dbe8abb` changed the tests to compare relative per-open increments. Stage 173 adds an independent host-mock regression proving that after close and reopen the cumulative tick count is retained, while the synthetic PCM tick clock, rolling PCM witness, pending queue and newly submitted audio start from their new-session state. This test exercises the unchanged production C audio adapter with ROM-free C mocks, and does not require a game image.

Separately, the older NeXium run `39152321654` completed successfully with a real guest-origin 900-tick audout record: 111 skipped submissions, zero added audio errors, and generated PCM observed on a virtual host audio sink. Those observations are not a causal A/B result, physical Switch playback or proven sound latency. The full Python CI for the stage-172 adapter fix was still pending at the last check; no stage-173 CI pass is claimed.

## Stage 174 — make release/guest audio lifetime comparisons uint32-safe

The stage-172 host mock fix compares lifetime diagnostic counters relative to each audio library's opening snapshot, rather than comparing absolute historical totals from libraries with different usage histories. This stage also preserves the adapter's *native 32-bit unsigned arithmetic*: per-open differences for `simulated_ticks` and `audio_errors` are now calculated modulo `2**32`. Without wrapping the subtraction, equal per-open increments across a `uint32_t` rollover could be falsely reported as a release/guest audio mismatch simply because the two libraries started from different lifetimes. All other diagnostics, including queue occupancy, submissions, releases and skips, remain unmodified per-session values. Two synthetic ROM-free regression tests exercise rollover and histories with different starting counters; no real-time emulator/hardware latency claim is made. The normal 900-tick release-vs-guest PCM witness check remains unchanged.

NeXium run 39152321654 previously reported a successful actual ROM-free Switch guest replay, including guest input events, generated PCM observed in the virtual sink and a bounded two-buffer audout stress record. The current Python CI and latest NeXium runs still require completion before this stage can be marked verified by CI. No runtime audio policy, ROMs, raw PCM assets, core gameplay or approved artwork are changed.

## Stage 175 — accept a 900-tick audio test that starts with queued pages

The actual ROM-free Switch guest replay in NeXium (run `39152321654`) recorded `audout_blocks_submitted=789`, `audout_blocks_released=790`, and two pages pending at the start versus one at the end of the 900-tick stress window. These values satisfy the conservation identity `start_pending + submitted - released = end_pending`. However, the metadata-only cross-run verifier erroneously assumed the queue began empty, so its `released > submitted` rule rejected an otherwise valid guest summary. Stage 175 corrects this by permitting **at most two pages of signed net queue change** during an observation window, consistent with the existing two-pending-buffer cap. When the fixed-ACK headroom probe is present, the stricter endpoint equality and capacity claims are still independently verified; overhangs of three pages and forged queue endpoints remain invalid. The patch includes five ROM-free regression methods covering one- and two-page carryover, impossible overhangs, a full release-position ledger, explicit endpoint forgery and two-run comparison acceptance.

This unblocks ingestion of legitimate NeXium observations; it does not prove that two independent trials had identical input/frame pacing, improved audio quality or lower latency. The real guest data mentioned above comes from an older successful NRO workflow, not CI validation of this patch. The complete Python CI and current NeXium jobs must still finish before marking Stage 175 green. No changes to guest audout runtime, queue admission policy, original arcade ROM/PCM or approved packaging artwork.

## Stage 176 — gate strict A/B skips on initial audio queue occupancy

Stage 175 allowed valid 900-tick NeXium reports with one or two pages released from a queue that was nonempty before the observation window. The descriptive A/B verifier previously matched six 150-tick render populations and single/first/later page-return counts but ignored this **initial queue capacity confounder**. Two runs may expose the same tick and ACK aggregates while beginning with different free audio slots. The ROM-free `verify_nexium_audio_mid_batch_ab.py` now validates the optional two-slot queue endpoints and their conservation identity (`start + submitted - released = end`), exports both endpoint values and matching metadata, and withholds the stricter `matched_exposure_and_returns_later_skip_*` deltas unless both reports have *confirmed equal starting occupancy*. Missing endpoint witnesses stay `null`, never an inferred empty queue. The older, explicitly weaker descriptive skip and ACK differences remain available.

Crucially **final queue occupancy is not required to match** for the strict per-window descriptive skip fields: it may be the consequence of changed admissions and is therefore reported separately as a diagnostic outcome, not used as a selection gate. Even identical coarse tick populations, matched ACK positions and equal queue starts do **not** prove per-call ordering, comparable host workloads, audio latency, or causal improvement. Five ROM-free test scenarios cover matching queue starts, different starting occupancy with equal returns and exposure, missing witness, forged queue fields and differing final occupancy. The production comparator still runs the independent complete guest report verifier before the A/B diagnostics. No guest sound buffer policy, ROM, PCM assets, game logic or approved cover art changed.

## Stage 177 — reconcile each 150-tick audout queue boundary

The ROM-free A/B verifier now reconstructs queue ownership **at each of the six 150-tick boundaries**, using independently validated window skip counts (which determine admissions), single/first/later page-return totals, and the witnessed initial queue occupancy. Each window obeys `pending_after = pending_before + (150 - skips) - released_pages` and must leave **zero, one or two** pending pages. The derived 900-tick submitted/released totals and the final witnessed queue occupancy must reconcile exactly. An intermediate impossible negative or over-capacity queue is rejected even if the net totals cancel across windows. Baseline and experimental queue-boundary paths are exposed separately in `baseline_queue_150tick_boundaries` and `experimental_queue_150tick_boundaries`, or `null` if endpoint evidence is absent. No exact per-call ACK sequence or comparable host timing is claimed.

Four new synthetic regression tests check all six well-balanced windows, an impossible two-page cross-window shift that otherwise cancels globally, a forged global submission total, and valid one-page release of a buffer already pending at the start of a guest stress window. Three earlier helper-only fixtures were made physically consistent: the canceled ACK reallocation uses one page in each direction, and the extra release / final occupancy cases now reconcile their implied page admissions. The ending queue occupancy remains an **outcome**, not a prerequisite for strict descriptive A/B skip comparisons. These are checks on audio report accounting only; neither the guest audio buffer policy nor the original arcade ROM, raw sound assets, gameplay and frozen art are changed. CI/NeXium results for this stage remain pending at publication.

## Stage 178 — measure uncontrolled baseline-to-baseline guest audio variation

The stage-177 GitHub Actions matrix for commit `74bcb8bf` completed successfully: **1,100 Python tests with one expected skip**, the Switch NRO bootstrap, host-native gameplay smoke, ROM-free public-tree privacy check, and actual NeXium guest replay all passed. The NeXium guest reported 900 audio ticks, 793 submissions, 792 page releases, 107 skipped admissions and zero added audio errors. Guest-origin movement/jump/attack traces and virtual monitor PCM were also observed. None of those observations proves physical Switch speaker audibility, low latency or arcade-audio equivalence.

Two independently captured *baseline* NeXium sessions, runs `39152321654` and `39156362936`, both reported **no opt-in mid-batch poll calls**, yet had differing baseline values: submissions 789 vs 793, page releases 790 vs 792, skips 111 vs 107, initial pending pages 2 vs 1, and batched-later tick populations 130 vs 175. This illustrates ordinary cross-run variability; the difference must not be presented as an improvement caused by the opt-in audio experiment.

A new ROM-free CLI, `tools/compare_nexium_audio_baseline_repeats.py`, pairs two **already-generated** 900-tick JSON stress reports. It reuses the complete stress-ledger and optional guest poll validators, requires both guest variants to have the extra poll disabled, and reports their aggregate differences, six per-window skip/return/exposure deltas and queue diagnostics. It explicitly marks host workloads, exact pacing, independence, physical audio, causal improvement and latency as **unverified**. Malformed, duplicate or experimental-mode reports fail closed. Example (private JSON paths; do not commit captured traces or original game files):

```sh
python tools/compare_nexium_audio_baseline_repeats.py \
  --first /private/guest-baseline-one.json \
  --second /private/guest-baseline-two.json \
  --out /private/baseline-repeatability.json
```

Seven ROM-free synthetic unit tests cover valid difference reporting, differing initial pending queues, rejection of missing required Stage-157 fixed-ACK headroom witnesses, improper A/B variant, duplicate metadata, falsified queue endpoints and CLI fail-closed behavior. This tool measures **baseline drift**, not treatment effects; no guest audio buffer policy, original ROM, user screenshots or approved packaging artwork changed.

The Stage-178 Python CI initially found one test-case inconsistency: the new comparison delegates to the established strict guest baseline validator, which requires a complete fixed-ACK headroom witness. A legacy report without that witness therefore cannot be classified as a comparable Stage-157 baseline. The test now correctly expects an explicit inconclusive rejection instead of falsely asserting that such metadata are sufficient. No change is made to the audio engine or the underlying accepted guest format.

## Stage 179 — safely preserve source guest evidence during baseline comparison

All five GitHub Actions workflows for Stage 178's corrected comparison at commit `cb640af1` have been assessed: Python CI completed successfully with **1,107 tests and one expected skip**; native ROM-free gameplay, privacy and Switch NRO bootstrap also passed. A guest NRO compiled successfully, while the NeXium guest execution was still running when these changes were prepared. Treat the last completed real NeXium run as the currently confirmed replay, not the pending run.

The ROM-free baseline-repeatability CLI previously used `Path.write_text` for `--out`, which could silently overwrite a private original JSON observation when the output path was accidentally set to `--first`/`--second`, overwrite an earlier comparison, or follow an existing symlink. Output now uses **exclusive creation** (`Path.open('x')`) so all existing files, including symlink targets and existing results, are protected. A collision or write failure emits an explicit inconclusive JSON status to stdout and returns nonzero, instead of publishing a false completed result. The original observation inputs remain untouched. Four ROM-free regression tests check fresh output, source-path collisions, preexisting results and symlink safety. **Only new destination files can be created.** No original ROM, private trace or raw PCM is included in the public commit.

For a new output, pass an unused path: `--out /private/baseline-repeatability-20261018.json`. If the file already exists, choose a new filename; the tool deliberately does not overwrite it. This affects only diagnostic file safety, not guest sound playback, buffer scheduling or cover artwork.

## Stage 180 — protect both NeXium A/B input reports from CLI output overwrite

The corrected Stage-179 baseline-repeatability tool passed all CI checks on commit `71976cd0`: Python tools, Switch native NRO bootstrap, ROM-free native gameplay smoke and the public ROM-free privacy gate. The NeXium NRO build succeeded; actual guest replay was still running when this change was prepared. The confirmed earlier emulator executions remain valid independent evidence, but are not substituted for a pending result.

The opt-in guest mid-batch A/B comparison command, `tools/verify_nexium_audio_mid_batch_ab.py`, also accepted `--out` and previously used `Path.write_text`, potentially overwriting either source guest report, a previous comparison or a symlink target. To preserve private guest execution evidence, the A/B CLI now writes **only to a new, nonexistent output path** via `Path.open('x')`. If the destination already exists or creation fails, it returns a nonzero exit code and a deliberately inconclusive JSON status on stdout rather than reporting success. The source files and existing results are never modified by `--out`. Four ROM-free regression tests cover successful new output, direct source collisions, an already saved result and a symlink to an input. This matches the safety policy of the baseline-repeatability CLI.

Use a fresh filename for each comparison, for example `--out /private/mid-batch-ab-20261018-01.json`; do not commit original game files, screenshots, host captures or private guest reports. This changes neither guest audio rendering, queue capacity, game controls nor approved cover art. The complete Stage-180 CI and emulator run must be checked separately before claiming a pass.

## Stage 181 — explicitly build experimental Nintendo Switch NRO for NeXium

A real A/B audio experiment requires **two independently built and executed ROM-free Switch binaries**, not only Python comparisons of synthetic reports. The existing `NeXium real Switch NRO guest replay` workflow now offers a `workflow_dispatch` choice `audio_mode`: `baseline` (the default, also used unchanged for automatic pushes and pull requests) or manually selected `extra-poll`. Both compile with `DINO_EMULATOR_SELFTEST`; only the opt-in mode additionally enables `DINO_AUDIO_EXPERIMENT_MID_BATCH_POLL`. Normal player-facing release builds never receive that diagnostic flag.

The build uploads its NRO, SHA-256 and selected-mode manifest together. The guest execution job verifies the mode manifest matches the requested workflow mode and checks the NRO hash *before* starting NeXium. After the actual ROM-free guest replay, `tools/verify_nexium_audio_mode_binding.py` requires a fully validated 900-tick audout report and matches the observed guest extra-poll flag and counts to the requested build: baseline must attest zero additional polls; extra-poll must attest exactly one nonblocking sweep for each batched later tick, with its real page ACK counts bounded by the guest ledger. Missing, inconsistent or mismatched guest observations fail closed; a successfully compiled experimental NRO by itself is **not** considered a guest execution pass.

Eight synthetic regression tests cover both correctly bound modes, mismatched mode/build declarations, forged counters, invalid full-ledger accounting, invalid mode inputs and successful/failing CLI results. To request an experimental run: GitHub Actions → `NeXium real Switch NRO guest replay` → **Run workflow** → `audio_mode: extra-poll`. The automatically triggered default workflow still uses baseline. Successful independent baseline and experimental guest runs must subsequently be compared using private JSON evidence and the existing descriptive verifier, without asserting matched host workloads or causal audio improvements.

This stage adds only ROM-free CI/test instrumentation. No original arcade game ROM, proprietary art or sound, physical Switch audio, user-supplied assets, or approved cover images are included.
 
## Stage 182 — archive a SHA-256-bound guest audio mode attestation with NeXium evidence

The Stage-181 manually selectable `baseline` and `extra-poll` NeXium modes already have build-time NRO checksums and a guest-side 900-tick audio validation gate, but the binding verdict was only printed to the GitHub Actions log. This stage persists the verdict in the same `dino-ne-xium-actual-nro-guest-evidence` artifact as the guest stress JSON. The mode verifier now includes `guest_report_sha256`, a SHA-256 digest of the **exact raw bytes** of the validated audio report, and accepts `--out` to write `emulator-evidence/guest-audio-mode-binding.json`. The artifact therefore keeps the report and its mode declaration side by side for later comparison; a hash alone cannot independently authenticate guest execution.

Output uses exclusive create (`open('x')`) rather than overwriting either report or an earlier verdict. Existing output paths, including symlinks, fail closed with an inconclusive JSON status and nonzero exit code. Five new ROM-free tests cover the digest, fresh persisted output, protection against overwriting the source guest report, previous attestation and symlink targets. NeXium now executes these tests before launching the emulator and uploads the sidecar on completion. A compiled NRO is not an attested execution: the attestation only succeeds if the recorded guest stress counters agree with the selected binary mode.

No automatic workflow switches to experimental audio: baseline remains default; the opt-in `extra-poll` run still requires a manual `workflow_dispatch` with that explicit input. Python CI, NRO build and NeXium verification for this stage must complete before claiming a green result. The original arcade ROM, sound/game assets, production audio policy and approved art are untouched.

**Stage 182 automatic PR-mode follow-up:** GitHub requires a workflow file on the default branch before the UI/API can receive `workflow_dispatch` events; this experimental workflow is currently in PR #54 rather than `main`. Instead of modifying `main` prematurely or claiming manual dispatch worked, the existing PR-triggered workflow now uses a two-value job matrix (`baseline`, `extra-poll`) for both compilation and guest execution. It attaches distinct per-mode build and guest evidence artifacts, so the new digest-bound mode attestations can be directly compared after both runs finish. Ordinary `push` checks still run the baseline only, and a future manual dispatch (once the workflow exists on the default branch) preserves the input-selected mode. `fail-fast: false` lets both PR modes report their own outcomes. The matrix is CI-only; game code, original ROM, private captures and released builds remain unchanged. See GitHub's workflow_dispatch event prerequisite: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatch.

## Stage 183 — compare both guest-origin NeXium audio modes in one PR run

The PR NeXium workflow now runs two guest builds and guest replays (`baseline`, `extra-poll`) and adds a `compare-pr-guest-audio` job depending on the completed replay matrix. The job downloads both guest evidence artifacts and runs `tools/verify_nexium_audio_paired_artifacts.py`: this checks each selected-mode binding against its original report's **exact SHA-256**, its complete 900-tick audio queue ledger, and the observed guest poll calls, then invokes the existing descriptive A/B comparison. Missing/forged evidence fails closed rather than asserting a successful experiment.

The resulting `paired-audio-comparison.json` is uploaded as `dino-ne-xium-bound-audio-ab-comparison`. It includes separate report digests and a descriptive summary, while explicitly leaving host timing, causality, physical Switch audio and sound latency **unverified**. Nine synthetic tests exercise valid pairing, swapped/forged modes and digests, edited guest reports, duplicate JSON keys, missing/symlinked bindings and non-overwriting output. For a normal PR, both modes execute on independent CI jobs; two separate host runs are not guaranteed identical workloads. The comparator is a provenance/accounting tool, not causal evaluation.

Current changes reside solely in Draft PR #54; release builds, original ROM, raw arcade audio, private captures and approved cover artwork are unchanged. Full CI and actual NeXium guest results for this commit are not yet verified.

## Stage 184 — bind A/B audio evidence to exact ROM-free NRO binaries

The paired guest audio comparison now checks the **actual executable binary** that produced each observed audio mode, not just the guest JSON and its mode attestation. `verify_nexium_audio_mode_binding.py` optionally accepts `--nro`, validates a bounded regular NRO with its `NRO0` header, and records `guest_nro_sha256` along with the guest-report SHA-256 in the mode attestation. NeXium's two guest matrix jobs supply the NRO they ran. The comparison job downloads each independently built NRO artifact and recomputes each attestation from the matching raw guest report and executable before allowing the descriptive A/B comparison. The paired verifier requires distinct baseline and extra-poll NRO hashes to prevent duplicate-binary comparisons from masquerading as two build modes.

Five ROM-free tests cover executable hash binding, invalid NRO files/symlinks, post-attestation binary mutation, identical executable bytes for different mode reports and symlink rejection in paired comparisons. The existing mode-binding tests without an explicit NRO remain compatible for local host-only fixtures, but **the GitHub guest replay and paired comparison jobs require actual binary hashes**. SHA-256 binds files; by itself it does not establish audio performance, emulator timing, original arcade equivalence or physical Switch playback. Results are unverified until current CI and both NeXium modes complete. No commercial game image or gameplay art/audio is added.

## Stage 185 — require internally consistent Switch NRO program size

The NRO digest verifier added in Stage 184 previously accepted any bounded file with the `NRO0` bytes at offset `0x10`. A corrupted synthetic file could therefore be cryptographically bound to a guest report without passing a basic Switch executable layout check. `hash_switch_nro` now also reads the little-endian declared program size at offset `0x18` and requires `0x80 <= declared <= actual_file_bytes <= 64 MiB`. Legitimate libnx files can append asset data beyond the program-size field; that case remains accepted and is fully included in the SHA-256 digest. Existing protections against symlinks, invalid magic, oversized files and mid-read size changes remain in place.

Three new ROM-free regression tests cover invalid declared sizes (including integer overflow-sized fields), valid synthetic append-only assets, and a forged program-size field in the paired A/B verifier. Synthetic test NROs were upgraded to include consistent Switch headers instead of relying on NRO magic alone. This improves evidence validation, **not** emulation accuracy or guest playback. No original arcade ROM, game audio or approved artwork is introduced. CI and both NeXium runs must pass before the stage is called verified.
 
## Stage 186 — repair POSIX devkitPro shell in two-mode NeXium build

The full Python CI for Stage 185 succeeded: **1,146 tests passed, one expected skip**. The standard Switch NRO bootstrap, native ROM-free gameplay smoke and tracked-source privacy gate also succeeded. However, the experimental NeXium build on run `39161325429` failed **before running make**: the devkitPro container invokes `/bin/sh`, which rejects the Bash-specific command `set -euo pipefail` with `set: Illegal option -o pipefail`. This was an orchestration shell mismatch, not an audio-admission or emulator result.

The container compilation step now uses portable `set -eu`. It contains no pipelines that require `pipefail`, retaining immediate termination on failed commands and unset environment variables. A ROM-free regression test checks the exact container build step, both selected modes and that Bash-only `pipefail` is absent. Both baseline and extra-poll builds must still compile and execute in NeXium, then complete their bound-evidence comparison before any functional audio result can be claimed. No game source, user ROMs, proprietary assets or frozen cover artwork changed.

## Stage 189 — prevent host HID fallback from restarting the guest audio stress interval

Real NeXium run `39162060538` compiled both distinct ARM64 NRO variants and completed the ROM-free 180-tick training-room replay in both. The **baseline** guest 900-tick audio mode was independently validated (797 submissions, 796 releases, 103 skipped, zero added guest errors). The **extra-poll** run also produced a complete CSV with 900 reported arena ticks, but the strict validation correctly rejected it: the first supposedly 150-tick window ran from guest audio tick 646 to 1281 (**635 audio ticks**, 485 too many), with 635 attributed render steps. As a result the extra-poll binding was inconclusive and the paired A/B job was skipped. No valid relative audio quality or skip-rate claim is possible.

The optional NeXium host pixel sampler may fail to witness a changed host pixel after **already delivering the complete original five-key guest HID sequence**. The old fallback used the *host pixel result alone* to decide to resend `Y` (reset), Right, attack, jump and spar. A redundant guest Y reset during the independent 900-tick stress window can invalidate the continuity of the arena tick counter. The extra-poll run's unsuccessful pixel sampler and subsequent malformed first 150-tick audio interval are consistent with this failure path; the precise guest key event causing the discontinuity has not been separately captured.

To avoid this interference, `tools/nexium_guest_replay_probe.sh` now consults `tools/nexium_hid_fallback_guard.py` **before** resending keys. The guard uses only fixed ROM-free names in isolated emulator directories. It suppresses a fallback if the guest controller CSV already attests `INPUT_DONE,31,...` or if **any** guest 900-tick audio stress CSV is present, even when empty or still being written. Missing or malformed private witness files fail closed. The backup sequence remains permitted when a readable controller file contains only an incomplete sequence and no audio stress run has begun.

Nine synthetic ROM-free regression tests cover complete/incomplete HID, active/empty stress files, malformed/oversized witness, symlinks, nested evidence directories, empty roots and ordering of the guard before fallback reset. The NeXium CI runs these tests before launching the emulator. The strict 900-tick guest validation remains unchanged; a noncontinuous guest clock must continue to fail. No game ROM, game engine/audio buffer policy, proprietary captures or approved cover art is changed. Confirm the new branch CI and actual extra-poll run before claiming this repair is verified.

## Stage 192 — completed NeXium A/B guest run and six-window skip concentration

All five workflows for commit `b1ce7b6c` completed successfully, including real baseline and extra-poll NRO guest replays and the final `compare-pr-guest-audio` job in GitHub Actions run `39163549127`. The paired artifact `dino-ne-xium-bound-audio-ab-comparison` was downloaded and inspected. Both exact guest JSON SHA-256 values and both actual NRO SHA-256 values match their saved mode attestations; each run has 900 valid guest ticks and six contiguous 150-tick boundaries.

Baseline: **808 submitted, 807 released, 92 skipped, no extra polls**. Experimental: **673 submitted, 674 released, 227 skipped, 220 additional polls, zero page releases by those extra polls**. Zero added audout errors in both. The two independent emulator jobs had unlike render batches (99 versus 220 later-batch ticks) and different starting queue occupancy (one versus two). The single 600–750-tick interval had 16 baseline skips versus 120 experimental skips, accounting for 104 of the 135 net additional skips. These figures are *descriptive observations only*: no matched host workload, causal improvement/degradation, true audio latency, physical Switch sound, or original arcade parity can be claimed.

The paired A/B verifier now publishes `window_skip_diagnostics`: all six skip deltas, reconciled per-run totals, a largest positive difference window and its exact rational share of all positive window differences, and an explicit false indicator for causal inference. Four ROM-free tests cover conservation, the observed synthetic 600–750 concentration case, misaligned/forged totals and malformed windows. The release audio mode stays unchanged. Next research should repeat both modes under more comparable guest batch exposure; one unbalanced pair is insufficient for an audio policy change. Pending new CI after this documentation and verifier update.

## Stage 194 — pre-registered identical frame/ack stimulus for the production C audio adapter

The two successful NeXium A/B pairs (runs `39163549127` and `39165011056`) disagree on skipped buffers because their **independent guest runs do not have matching per-window frame-batch populations or initial queue occupancy**. Consequently neither run establishes a causal audio effect. The opt-in mid-batch poll stays disabled for release.

Before altering the emulator or normal player code, introduce `tools/nexium_audio_control_plan.py`, a ROM-free, hashed deterministic **host-only** test stimulus. Each variant begins with **two submitted and pending audout pages** before the 900 observed ticks. Each of the six 150-tick windows uses exactly 15 repetitions of frame sizes `[1,2,3,4]`, resulting in 90 single-tick frames, 270 first batched ticks and 540 later batched ticks across all windows. A simple fixed per-tick 0/1/2 external ACK-credit function supplies the *same sequence* to both variants; it is not a model of real NeXium timing.

`tests/test_nexium_audio_controlled_mock.py` builds two **separate native shared libraries from the real production C adapter** against the established audout mock: one without the experiment, one with both guest self-test and opt-in extra-poll defines. It initializes the two queues identically and replays the exact same 900 audio events, frame boundaries, and ACK credits. It checks queue occupancy, submitted/released/skipped ledgers, PCM synthesis hash and audio service integrity throughout. Only the experimental library may call the additional nonblocking poll at the 540 later-batch positions. Four additional plan tests lock the schedule, six window boundaries, digest and exclusive artifact creation.

The NeXium PR comparison job also runs the C host experiment and archives the full `controlled-host-audout-plan.json` alongside the **separate** guest A/B report. Their evidentiary scope must remain distinct: success demonstrates deterministic queue handling under synthetic identical inputs; **it does not imply matching real guest frame pacing, ACK timing, native Switch speaker output, original arcade sound or causal improvement**. The normal gameplay sound pipeline and private ROMs remain unchanged. This stage is unverified until its new GitHub CI passes.

## Stage 195 — verified deterministic C test and recorded per-window native counters

The Stage 194 commit `450c1e94` **passed the complete CI**, including 1,166 Python tests (one expected skip), both real NeXium 900-tick guest runs, the descriptive guest A/B report, native gameplay, the production Switch build and privacy review. The ROM-free controlled host C-adapter test passed in both Python CI and NeXium's comparison job. The exported stimulus has 360 render frames, 900 audio ticks, two prefilled audout pages, 540 guest-only extra-poll positions and digest `34fd40a1936362d7f50938725f529ba525bcca98c27151ed938eff920aadb7f1`.

The actual guest results remained **uncontrolled**: baseline submitted 785, released 786 and skipped 115; extra-poll submitted 777, released 777 and skipped 123, with 240 extra polls and one page released by an extra poll. Different later-batch populations (172 versus 240) preclude a causal conclusion.

This stage adds a second, *observed* output for the deterministic native C exercise: `controlled-host-audout-result.json` with six 150-tick rows and actual submitted, released and skipped ledger deltas from **both independently compiled production C adapters**, a verified plan SHA-256, experimental poll count and explicit evidence-scope limitations. Publication happens only **after every simulated tick passes queue/PCM equality assertions**, the six windows reconcile, and both guest-only experimental mode flags are checked. The artifact is created exclusively, never replacing an earlier file. CI independently checks that the observed report links to the exact retained input stimulus and archives both alongside the distinct real NeXium comparison.

The native double can establish deterministic counter parity under the prescribed synthetic ACK schedule, **not equal NeXium timing or real hardware playback**. No production audio behavior, original game ROM, commercial media or approved artwork changed. This additional result must pass CI before publication is considered verified.

## Stage 196 — independently verify measured native C audio ledgers (ROM-free)

All five workflows at Stage 195 head `cef9c023` completed successfully. Real NeXium [run `39167303205`](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39167303205) includes two successful experimental NRO builds and guest runs, the A/B guest comparison, and the new deterministic host mock artifacts. The **controlled host C results** under the single committed 900-tick plan were independently inspected: baseline and extra-poll **each admitted 416, released 416, skipped 484** within the measured window, with two pages already pending at start. The experimental path made 540 additional polls, which accounted for 249 page releases. For every six 150-tick windows, the counter deltas were identical. This observed parity is specific to externally granted, deterministic host mock ACK credits.

The real uncontrolled NeXium runs remain different: baseline skipped 52 audio blocks and had 31 later-batch ticks; experimental skipped 117 and had 146 later-batch ticks, with two releases detected by 146 extra polls. Different native emulator schedules **do not permit a causal conclusion**. The release build's audio scheduling is unchanged.

`tools/verify_nexium_audio_controlled_oracle.py` now provides a *separate pure Python accounting oracle*, calculating all 900 admission, release, pending and skip outcomes from the pre-registered host plan without loading or calling the C implementation. It independently checks **every** measured 150-tick window, the 416/416/484 ledger totals, 540 extra poll positions, and 249 credits picked up by the additional sweeps. It recomputes expected evidence fields rather than accepting self-reported "passed" flags. The guard rejects duplicated JSON keys, symlinks, oversized or truncated evidence, changed plans even with recomputed hashes, bool-versus-int type substitutions, false device claims and any counter forgery. It exclusively writes a SHA-256-bound `controlled-host-audout-oracle.json` and fails closed on mismatches. Eight synthetic regression tests protect these constraints. GitHub CI runs the independent check after the two native C binaries and preserves its attestation next to the host plan, host C report and separate NeXium guest comparison.

This is independent **source-level arithmetic cross-validation for the synthetic host audout mock**. The ACK-credit law, PCM samples and frame schedule are synthetic; the oracle does not establish hardware playback, native NeXium timing equivalence, original game sound or a causal effect from polling. CI for this new revision must pass before the new check is considered verified.

## Stage 197 — six pre-registered host-only ACK schedules for two real C audio adapters

The prior head `2a4fda5f` passed all five GitHub workflows. The paired actual NeXium run `39168230111` validated 900 guest ticks in both modes, and the extra audout **host-only** evidence was checked independently against a second pure Python queue oracle. Under the original identical host stimulus both C binaries submitted 416, released 416 and skipped 484 over the observation window; all six windows matched, and the optional 540 extra polls observed 249 of the externally supplied releases. This proves counter parity under one artificial release-credit schedule, **not** hardware audio benefit.

Stage 197 adds a **fixed six-scenario** synthetic stress corpus in `tools/nexium_audio_release_corpus.py`, retaining the 360-frame/900-tick distribution, prefilled two-page queues and identical deterministic PCM events across modes. The six predefined release-credit schedules are: `none` (zero credits), `steady` (one per tick), `first-only` (one credit at the first tick of a render frame), `later-only` (one credit at later ticks), `burst-11` (two credits every eleventh tick) and `original-mix` (the existing Stage 194 mixed schedule). The entire corpus is SHA-256 bound; changed schedules are rejected even if their digest is recomputed.

`tests/test_nexium_audio_release_corpus.py` compiles the two unmodified production C adapter variants independently and applies **all six scenarios** with exactly matching external credits and frame boundaries. For every one of the 5,400 observed ticks per mode, it checks queue ownership, PCM witness parity and admissibility; after each 150 ticks, it captures actual per-mode submitted/released/skipped ledgers and how many external release credits the extra polls detected. A separate pure-Python queue oracle computes expected results from the pre-registered inputs, without reading or calling C. Negative tests reject forged reports, modified schedules, JSON type confusion, symlinks and overwrites.

The NeXium comparison job now stores three *host-only* files alongside the separate bound guest evidence: `controlled-host-release-corpus-plan.json`, `controlled-host-release-corpus-result.json` and `controlled-host-release-corpus-attestation.json`. Every test and attestation distinguishes host mock equality from independent real NeXium timing and physical audio: no causal improvement, speaker playback or original arcade sound parity is claimed. The real game engine, ROM handling, approved covers and ordinary release sound mode remain unchanged. The new CI must pass before the expanded experiment is verified.

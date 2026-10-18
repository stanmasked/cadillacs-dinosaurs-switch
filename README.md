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

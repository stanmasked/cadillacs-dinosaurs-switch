# Testing the ROM-free Switch NRO in an emulator

This is a **manual emulator-based QA procedure** for the independently
authored CPS-1 Research Arena technical homebrew. This is **not** a
claim that an emulator run has already succeeded.

## 1. Obtain the correct NRO

Open the [Nintendo Switch native bootstrap GitHub Actions runs](
https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions)
and download the NRO build artifact from a successful run for the
specific source commit under test. The artifact includes a SHA-256
checksum. Verify it locally, and use the `cadillacs-dinosaurs-switch.nro`
file. Do not copy or publish personal prod.keys, firmware, ROM archives,
game graphics, or private captures into the repo.

An NRO already built for an earlier commit tests **that earlier commit**
only: merely having an NRO file does not validate the latest code.

## 2. Prepare an emulator

Use a locally installed Nintendo Switch emulator that supports opening
homebrew NROs (for example a compatible Ryujinx-derived build).
Install/setup according to its own instructions. If it requires
firmware or device keys for the chosen configuration, use only
software and data you are entitled to use, kept privately outside
this project. **The ROM-free training room itself does not read any
commercial game's ROM.**

On Linux/macOS, the conservative probe can attempt to launch the
emulator's executable with the NRO as its final argument:

```sh
python3 tools/switch_emulator_launch_probe.py \
  --emulator /absolute/path/to/emulator \
  --nro /absolute/path/to/cadillacs-dinosaurs-switch.nro \
  --sha256 YOUR_VERIFIED_NRO_SHA256 \
  --runtime 10
```

For custom launcher arguments, repeat `--emulator-arg OPTION` before
the NRO. The probe deliberately **does not** install emulators,
download keys or firmware, read private emulator configuration, or
collect full emulator logs. It will terminate its direct child process
after the bounded interval. Do not run it against an existing shared
emulator session with unsaved work.

The SHA-256 argument is optional but strongly recommended: use the
64-character digest from the successful GitHub Actions NRO artifact.
The probe does not copy that value into its JSON output. In addition
to `NRO0` and total size, it independently validates the three
bounded and nonoverlapping, 4 KiB-aligned text/rodata/data sections.
A symlinked NRO is rejected. These static checks still cannot prove
that instructions are compatible with a particular emulator.

Possible machine results are `INVALID_NRO`,
`INVALID_CHECKSUM_ARGUMENT`, `NRO_CHECKSUM_MISMATCH`,
`EMULATOR_UNAVAILABLE`, `EMULATOR_EXEC_FAILED`,
`EMULATOR_EARLY_EXIT`, or `PROCESS_ALIVE_RENDER_UNVERIFIED`.
**No result means "gameplay verified".** A surviving process only
shows that the emulator process did not exit during that observation.
For GUI launchers that detach a child process, an early exit can be
a false negative and requires manual inspection.

## 3. Manually verify the training room

Without any `gfx.bin` file, the NRO should start the
**ROM-free training arena**. Visually confirm the HUD and background,
then exercise:

- D-pad movement in both horizontal and depth directions;
- B jump; A punch; a three-hit combo and the finisher effect;
- X toggles the optional invented sparring opponent;
- moving/jumping to dodge a telegraphed attack;
- Y resets the fight; + exits cleanly.

On the technical audio HUD, distinguish `AUDIO ON` (service started)
from audible sound. Listen for new, independently synthesized cues
during punching, jumping, hitting and dodging. Record skipped-block
and error counts; playback sound and latency are **unverified**
until directly observed by a person/test capture. If sound is
unavailable, controls and rendering should continue working.

When user-local, properly owned diagnostic `gfx.bin` is available,
ZL should toggle back to the legacy tile/scene viewer. A protected
game ROM or asset file is **not required** for the training test.

## 4. What can be claimed

There are three distinct evidence levels:

1. **NRO built:** devkitPro toolchain successfully compiled the file.
2. **Emulator process survived:** conservative launcher probe remained
   alive during a bounded window. This does not prove a displayed frame.
3. **Emulated gameplay verified:** a tester observed the actual
   ROM-free training room, controls, visual effects and, separately,
   audible audio in an emulator. Report emulator name/build, NRO
   commit SHA, observations, and any failures without uploading
   personal keys, firmware, ROMs or private log paths.

The new host-side regressions only exercise synthetic file format
validation, process-availability and early-exit behavior using the
system Python interpreter as a **mock executable**. They do not
pretend to be a real Switch emulator. No original CPS-1 gameplay,
sound parity or physical Switch hardware parity is implied.

## Built-in 180-tick emulator controller self-test (stage 126)

The same **ROM-free, 180-step C input trace** now lives in
`source/dino_replay.c` and is compiled into both the actual
Nintendo Switch NRO and the independently executable Linux desktop
preview. The two consumers no longer maintain duplicate Python/ARM
scripts that might drift. The trace moves the training actor towards
the stationary dummy, delivers a three-hit finisher, turns on sparring,
attacks again and attempts a jump. No original game ROM, CPU trace,
asset, keys or external controller automation is required.

When the training-room NRO is **actually running** in a Switch
emulator, press the **Minus (-)** controller button once.
The NRO resets the arena and advances one trace input on each
60 Hz simulation tick. After 180 steps (3 seconds of *simulated*
gameplay, not necessarily 3 seconds of wall-clock if the emulator
runs slowly), its frame and HUD remain frozen until **Y** resets.
The HUD prints:

`C REPLAY 180/180  DONE - Y RESET  HP 4  HITS 3`

The independent native-host run of the same C trace already
verifies: player `x=230`, player HP `4`, three confirmed hits,
and sparring mode enabled. The complete desktop raster and
synthesized PCM stream have additional reproducible digests,
but those digests are **not** claims about the Switch GPU or
audio service. The pause-on-completion mode simplifies manual
inspection and screenshots in an actual emulator.

Controls: **Minus** to restart the trace at any moment;
**Y** to return to normal control; **Plus** to exit.
When user-owned `gfx.bin` is present, switch to the
training room via ZL first. During automated replay, normal
D-pad/attack inputs are intentionally ignored, so test results
are independent of physical controller timing.

This is a meaningful *precondition* for eventual genuine Switch
emulation. A success claim requires actual emulator execution and
observation of the final NRO frame, not a host simulation test or
a unit test of the control trace.

## Stage 127 — deterministic on-screen cross-platform state fingerprint

The ROM-free 180-step controller trace now emits a **canonical state
fingerprint** using `source/dino_replay_witness.c`. At every 60 Hz
gameplay tick, the exact same code serializes a selected set of
integer combat state fields and event flags explicitly as
**little-endian 32-bit values**, in a documented fixed order, then
updates a 64-bit FNV-1a digest. This method never hashes C struct
padding, memory addresses, emulator-private data, ROM bytes, or
original Capcom gameplay.

The actual Switch NRO's frozen replay frame now displays
`STATE FNV64 <16 hexadecimal digits>`. The host preview's
`--headless --ticks 180` JSON also reports
`gameplay_witness_fnv64` produced by the exact same portable C.
The two values should match after the same 180 replay steps.

The verified native-C stage-127 reference is:

```text
C REPLAY 180/180 DONE
STATE FNV64 5BCA2FF01FB244F6
HP 4   HITS 3   SPAR ON
```

The code was independently captured in the GitHub Actions
`host-witness.json` and is locked in a Python regression and the
ROM-free visual smoke workflow. Treat a different on-emulator digest
as a simulation/state mismatch even if the characters visually look
right. A matching digest is not proof of emulator sound or GPU pixels.
This will help distinguish state divergence from renderer-only
differences when a compatible Switch emulator becomes available.

The fingerprint covers, in order: simulated tick, actor X/Y/Z
and jump velocity, dummy X/Y, accumulated hits, event mask, two
health values, combo count, sparring flag and current pose values.
A Python-independent little-endian implementation verifies the
C hash after **every** replay step in the host CI, not just at
the final frame. Changing any one of several critical scripted
inputs must change the final digest. Null arena pointers must
leave the digest unchanged.

**Evidence boundary:** a matching value in an actually displayed
Switch emulator frame would confirm only parity of these selected
simulation values and event sequence. It would not independently
verify actual GPU pixel output, audible PCM or original MAME
Cadillacs and Dinosaurs gameplay.

## Stage 128 — independently check generated PCM in an emulator

Alongside the stage-127 gameplay-state fingerprint, the NRO's
**Minus** replay now shows an additional line after 180 ticks:

```text
STATE FNV64 5BCA2FF01FB244F6
PCM FNV64 D82C3B7960857B22  BLOCKS 180
```

The PCM fingerprint is the FNV-1a digest of **every synthesized
48 kHz, 16-bit, stereo sample for 180 game ticks**. Samples are
hashed before they are submitted to libnx `audout`, or written
into a scratch buffer when audio is unavailable. The same portable
C helper `source/dino_pcm_witness.c` is linked into the NRO and
the Linux native gameplay preview. The reference value was
independently recorded in a previous passing native-host
GitHub Actions artifact, before the common witness code was added.

For future emulator QA, compare **both** values in the frozen NRO
HUD with the host witness file. A matching PCM digest means
the original self-authored procedural synthesizer generated an
identical sample stream. It **does not** demonstrate that libnx
accepted, queued, emitted or audibly played these samples, and
does not establish emulator latency, console speaker output or
parity with any commercial game audio. Check the separate
`AUDIO ON/OFF`, queued, skipped and errors HUD indicators;
audibility must be confirmed independently by actual emulator
playback or listening tests.

Five ROM-free tests independently implement PCM FNV using Python,
exercise signed-sample endianness, chunk boundaries and error
inputs, detect single-sample changes and pin the original
180-tick native-C golden value. The visual smoke workflow
requires both the state and synthesized-PCM digests to match.

## Stage 129 — real NeXium ARM64 NRO guest execution attempt in CI

A **separate optional** GitHub workflow, `NeXium real Switch NRO
guest replay`, now cross-compiles a special NRO with the
`DINO_EMULATOR_SELFTEST` build flag, loads that actual ARM64 homebrew
binary under a pinned NeXium experimental nightly and requests
software Vulkan through Mesa Lavapipe/Xvfb. It does not need any
commercial game ROM, console firmware or Nintendo encryption keys.
The standard user-facing NRO does **not** auto-start a replay or
write guest reports; the diagnostic flag is enabled only for the
standalone emulator CI build.

This isolated test version starts the same ROM-free 180-tick replay
without simulated keyboard events. Inside the running **Switch guest**,
it attempts to create `sdmc:/cadillacs-arena-selftest.csv`
on the emulator's virtual SD device, then records three checkpoints:

- START: training room reset before any simulation tick
- FRAME_SUBMITTED: native NRO code passed `framebufferEnd` after an
  advancing tick; this is not guaranteed visible host GPU pixels
- REPLAY_DONE: 180 simulated ticks, player x=230, HP 4,
  three confirmed hits and generated-PCM blocks=180, with
  `STATE FNV64 5BCA2FF01FB244F6` and
  `PCM FNV64 D82C3B7960857B22`

The workflow isolates the emulator home/config/data directories,
checks the pinned official nightly archive's SHA-256 before executing
it, and accepts a PASS only when a strictly validated, **guest-created**
report was recovered from that isolated virtual SD tree.
The evaluator rejects missing/extra events, invalid ticks,
malformed hex, altered gameplay or PCM codes and unexpected report
sizes. A process surviving, UI window appearing, emulator timing
out, or the host's synthetic fixtures **cannot** pass this test.
If guest SD mounting or rendering is unsupported by that NeXium
nightly, the outcome is explicitly **INCONCLUSIVE**, not fabricated
emulator success.

The optional captured emulator window may help diagnose software
Vulkan rendering, but the two guest hashes prove only selected
gameplay-state and generated-PCM equivalence. Separately measured
host-screen pixels and audible device sound are still unverified
unless directly inspected and tested. Both the installation and
result records are kept in short-lived GitHub Actions artifacts.

### First confirmed real NeXium homebrew runtime — 18 October 2026

Unlike all previous desktop-only tests, the independent
[NeXium run #39116927210](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39116927210)
**completed the actual ARM64 NRO's 180-tick replay in the emulator**.
The guest-created `cadillacs-arena-selftest.csv` includes:

```text
START,0,90,5,0,CBF29CE484222325,CBF29CE484222325,0
FRAME_SUBMITTED,3,96,5,0,4672EA392DD89A2A,1679C52CD5075125,3
REPLAY_DONE,180,230,4,3,5BCA2FF01FB244F6,D82C3B7960857B22,180
```

The real Xvfb/NeXium emulator window was independently captured at
**1280×720**. It visibly shows the self-authored teal actor, ochre
opponent, HUD and arena. Pixel inspection confirmed training-room
background `RGB(30,61,70)`, depth-lane `RGB(62,83,74)`, teal
actor `RGB(62,180,208)`, ochre opponent `RGB(190,126,74)` and
lower HUD `RGB(11,18,29)`. This is a **real displayed homebrew
frame**, not a copied host preview. A subsequent CI refinement now
requires those exact colors (at fixed unobstructed coordinates)
before accepting a green emulator-rendering check.

The experimental NeXium guest reported the expected training-room
state and generated PCM hash. However, the CI host had **no ALSA
default sound card**. It is therefore still incorrect to claim
confirmed audible audio, actual speaker delivery or original game
fidelity. This emulates the new ROM-free geometric training-room
prototype, **not commercial Cadillacs and Dinosaurs**. Real original
MAME captures/gameplay remain a separate unresolved task.


## Stage 130 — actual guest audio-service accounting (not audible audio)

The diagnostic DINO_EMULATOR_SELFTEST NRO now records **eight additional
integer fields** in its own emulated-SD replay CSV at START,
FRAME_SUBMITTED and REPLAY_DONE. They are obtained directly from the
guest dino_switch_sound_diagnostics() function:

- audio_ticks: 60 Hz audio adapter step count, required to match
  the corresponding simulation tick count.
- audio_active and audio_queue_valid: libnx audout service and
  logical output buffer-accounting state.
- audio_pending, audio_submitted, audio_released, audio_skipped:
  outstanding pages, native buffer submissions/releases and drops.
- audio_errors: failures in the guest's audio adapter.

The verifier checks the maximum of two queued blocks, equality of
submitted - released == pending, finite per-tick counters, valid 0/1
flags, and matching guest simulation/audio tick counts. Malformed or
contradictory reports are **INCONCLUSIVE**, not successful audio output.
An unavailable emulator sound device remains a **valid silent fallback**:
all 180 ticks of the deterministic replay and synthesized PCM hash
must still advance.

A positive submitted count means that some blocks were accepted by the
libnx audout API. It does **not** establish that the host sound system,
a speaker, headphones, or a human heard anything. The generated PCM
FNV64 remains a pre-audout witness, not a recording of physical sound.
The machine-readable device_audio_audible_verified flag remains false
even if submitted/released counts increase.

This extra telemetry exists **only** in the emulator-CI homebrew build;
the ordinary NRO never writes this self-test report. No game ROM,
commercial artwork/audio, user firmware, private keys or private
controller recordings are collected. The validator schema is v2.
The new ROM-free regression suite checks counter corruption, silent
fallback, invalid flags, missing fields and tick mismatches.


## Stage 131 — isolated host virtual-sink PCM observation

The real NeXium ARM64 guest replay workflow now **optionally** sets up a
private PulseAudio null sink, routes its default ALSA output through the
same server, and records the null sink's **host monitor** as raw stereo
48 kHz signed-16 PCM. This uses only the ROM-free prototype and does not
require Nintendo firmware, original game audio, commercial ROM content,
a sound card or personally owned keys.

The new tools/verify_nexium_host_audio.py checks the stream in bounded
chunks (at most 32 MiB) and looks for multiple 100 ms windows with
meaningful samples rather than accepting a single accidental nonzero
sample. Only sanitized summary numbers are uploaded; **the raw audio is
not a CI artifact**. Synthetic unit tests cover signal, silence,
insufficient activity, malformed data, large files and symlinks.

- VIRTUAL_SINK_PCM_DETECTED: the isolated host virtual sink's monitor
  actually contained non-silent samples. This is a stricter signal
  observation than guest-side generated PCM FNV and audout queue counts.
- INCONCLUSIVE_NO_HOST_SIGNAL or INCONCLUSIVE_CAPTURE_UNAVAILABLE: host
  playback could not be observed; the guest gameplay evidence remains
  independently valid and is not falsely described as audio success.
- Neither condition proves audible loudspeaker/headphone playback,
  perceptual audio quality, latency or original Capcom QSound parity.
  Physical/audio listening remains a separate uncompleted requirement.

This check is diagnostic-only; it does not modify the regular NRO,
the arcade reference path, approved artwork or the main branch.


## Stage 132 — actual external HID input through NeXium (optional)

The diagnostic-only NRO attempts a second verification after the
independent built-in 180-tick replay is complete. The NeXium CI window
first captures the proven ROM-free gameplay screenshot. It then sends
ordinary X11 keyboard events using the default keyboard bindings
published in NeXium's open-source `controller_config.rs`:
Z = Switch Y (reset), ArrowRight = D-pad Right, C = Switch A
(attack), X = Switch B (jump) and V = Switch X (toggle sparring).

**Crucially, the script's attempt to send keys is not evidence.** Only
the running guest's `padGetButtonsDown` / `padGetButtons` interface
can reset the arena, cause an actual character movement, and generate
the appropriate ROM-free attack, jump and sparring event flags. A
separate guest-created `cadillacs-controller-selftest.csv` is written
with a reset checkpoint and an `INPUT_DONE` record *only* when all
four effects are observed inside the NRO. The file contains only a
short bitmask, player X-coordinate and sparring state; no personal
controller history or host keyboard timestamps.

The independent `verify_nexium_guest_controller.py` rejects absent
files, partial sequences, mixed/extra rows, incorrect flags or player
coordinates, malformed fields and symlinks. It returns
`GUEST_HID_EFFECTS_WITNESSED` only for a complete native guest report;
otherwise it records `INCONCLUSIVE_NO_GUEST_HID_EFFECTS`. An
inconclusive optional input test does not invalidate separately proven
180-tick guest execution, host pixels, or virtual-sink sound.

This optional test cannot measure input latency or confirm hardware
Joy-Con/Pro Controller compatibility. Nor does it validate original
commercial-game controls. The standard consumer NRO does not enable
the CI-only witness or write controller diagnostic files.


## Stage 133 — ordered guest HID effect witness in simulation ticks

The real NeXium test now includes a **second, independently verified
controller witness** emitted by the running diagnostic ARM64 NRO:
`cadillacs-hid-timeline.csv`. It records RESET at guest tick zero,
then actual MOVE, ATTACK, JUMP, SPAR and DONE checkpoints, including
integer simulation ticks, actor X coordinate, sparring flag and in-game
one-tick event mask. The CSV is created only after an actual guest HID
Y reset following the original 180-tick ROM-free replay. Normal homebrew
builds do not create this file.

The new Python verifier refuses missing/extra/reordered rows,
out-of-range values, absent in-game attack/jump/spar event bits,
non-advancing action ticks, leftward coordinates in this rightward-only
test, inconsistent sparring state, and any disagreement with the
separate confirmed 31/31 controller-effects summary. There are twelve
new synthetic rejection/contract tests. The workflow exports only the
short guest-owned report plus a bounded JSON summary.

The four tick intervals (reset-to-move, move-to-attack, attack-to-jump
and jump-to-spar) are **guest simulation intervals**, not real-world
milliseconds. They establish action ordering and internal progression
only. Neither host-to-guest keyboard delay, screen/display latency,
physical Joy-Con behavior nor audio output latency has been measured.
Never convert a guest tick count into an external latency claim.


## Stage 134 — sampled host keyboard-to-emulator-window response bound

This optional **software-only** measurement starts after NeXium has finished
the independently validated 180-tick NRO replay. The host first sends the
default Y-reset keyboard event to the actual emulator window and verifies
two pixel baselines in the ROM-free training room: player body at
(334,425) is cyan, prospective movement position (361,425) is green.

Using a single host monotonic clock, the new tool records an instant just
BEFORE sending D-pad-right key-down and completion of the first host X11
1x1 screenshot that contains cyan player-body color at (361,425).
Elapsed time is rounded UP to milliseconds. It includes keyboard
injection, emulator scheduling, rendering, X11 capture and sample
processing. This is a conservative sampled **host software-window
response upper bound**, not a precise intrinsic input latency; actual
transition could happen earlier between samples. The tool then delivers
the existing A attack, B jump and X spar-mode keys.

The host JSON intentionally records HOST_PIXEL_CHANGE_OBSERVED_UNBOUND
and does not claim guest binding. The independent
verify_nexium_host_input_bound.py accepts it only with an independently
verified native guest RESET→MOVE→ATTACK→JUMP→SPAR→DONE timeline and
matching 31/31 guest effect summary. A missing sample, unexpected
pixel color, forged measurements or an inconsistent guest trace
leave the result INCONCLUSIVE. Failure of the optional sampler falls
back to the established host keyboard sequence, preserving the original
guest-HID validation.

No screenshots, raw keys, original game data or absolute timestamps are
uploaded. The sanitized JSON contains only measurement type, bounded
interval and sampling count.

This is NOT a hardware Switch/Joy-Con/Pro Controller latency,
physical display first-light measurement, direct emulator HID delay,
audible output timing, original Capcom arcade parity or sound latency.
Host load and capture frequency influence the observed bound.


## Stage 135 — sampled Pulse-monitor response to actual guest spar action

After the established NeXium 180-tick replay, keyboard reset/move,
A attack and B jump, the test starts a **second, optional** recorder
for the isolated PulseAudio null-sink monitor. The ROM-free sound
engine already defines an original training-room spar-toggle cue:
an approximately 530 Hz triangle tone lasting five 60 Hz ticks.
This cue is not from the Capcom arcade game, ROM, or QSound assets.

A separate host monotonic clock is sampled just **before** sending
the X11 V key (emulated Switch X / spar mode). The host script first
samples the monitor for at least 400 ms and rejects non-silent
baselines or insufficient PCM. It then sends the spar-toggle
command and watches for at least 20 meaningful PCM sample frames.
If detected, the elapsed time is rounded up to milliseconds and
reported as a coarse **host key-command to sampled Pulse monitor read
upper bound**. The bound includes host keyboard dispatch, the
emulator, guest libnx audio queue, Pulse server scheduling, recorder
pipe buffers and host monitoring overhead. It is not the precise
instant the original tone was generated or heard.

The new verifier requires independent proof that the running ARM64
NRO actually processed the ordered reset/movement/attack/jump/spar
events, matching the original 31/31 HID summary. No original
commercial audio, raw waveform, host keyboard recording, private
paths or absolute timing information is uploaded. Only two small
sanitized JSON files (raw host diagnosis and bound evidence) can be
retained.

Silent/unsupported Pulse monitors, prior jump/landing audio in the
quiet baseline, lack of observed tone and inconsistent guest events
must produce **INCONCLUSIVE**, not invented latency or sound
success. If the optional recorder cannot start, the final spar key
is still delivered to preserve the older, independently verified
HID test.

Even if the report succeeds, it does NOT establish physical Switch,
Joy-Con, headphone/loudspeaker output, acoustic onset, calibrated DAC
latency, game-quality audio or fidelity to Capcom's QSound originals.
This remains a ROM-free training prototype and a host-software
measurement.


## Stage 136 — discriminate the actual ROM-free 530 Hz spar cue

The original stage-135 monitor contract detected any meaningful
post-key PCM, provided its preceding Pulse monitor baseline was silent
and the native guest HID sequence ended with a SPAR event. That is
useful for observing audio activity, but alone cannot exclude every
unrelated game cue that might arrive after pressing V.

Stage 136 scans at most 32 overlapping windows of 2048 stereo
frames (1024-frame hop) after the first significant post-key monitor
sample, without writing raw audio to disk. The bounded memory buffer
permits the first candidate to contain an older, delayed jump or landing
effect, while a later candidate can still reveal the actual SPAR cue.
It computes normalized energy coherence of the left-channel fundamental
against the known 530 Hz tone synthesized by the ROM-free
SPAR_TOGGLE event. Without a full qualifying window scoring at least
0.60 the result remains **INCONCLUSIVE**, not a successful sound
response. Only a bounded summary of windows scanned and best
coherence is retained for diagnostics, never raw audio. A threshold-only noise spike, different-frequency tone or
unexpected silent signal cannot establish the 530 Hz marker.
The sanitized report contains only a coarse integer coherence score,
expected reference frequency and the host monitor-read response bound.

The input-to-monitor value still includes X11 keyboard dispatch,
emulator scheduling, guest libnx audout, host Pulse scheduling and
monitor read/analysis overhead. It is an upper bound of **sampled
software audio monitor response**, NOT an onset timestamp, acoustic
latency, physical Nintendo Switch output or Capcom QSound parity.
Unaltered guest HID and original 180-tick replay checks still gate
the interpretation. This strengthening does not replace or re-label
the independently confirmed stage-135 numbers as frequency-verified:
those earlier measurements were threshold-only.


## Stage 137 — 900-tick native audout queue stability after actual HID

After the ROM-free NRO's independently proven 180-tick replay and
genuine reset/right/attack/jump/spar input, the **same running ARM64
guest** records 900 additional fixed-60Hz arena/audio steps (15 seconds
of nominal simulation time), without requiring original game assets.

At the actual guest start, and after every 150 more steps, it writes
a short CSV checkpoint containing the arena tick, synthesized audio tick,
PCM tick, the running PCM checksum, audout service state, pending queue
pages, submitted and released buffers, skipped blocks, and backend errors.
There are exactly seven rows: START, five CHECKPOINTs, STRESS_DONE.
No waveform data, keyboard history, absolute host timestamps, ROM
resources or user-owned paths are published.

The separately tested validator checks that every 150-tick segment
actually advances the *guest simulation*, the synth and the PCM checksum;
that each generated tick is either submitted or dropped, not both; that
the libnx bookkeeping remains balanced (submitted - released = pending)
and never admits more than two simultaneously outstanding pages; that
submission continues in every segment; and that the audout service stays
active with no added errors. It also binds the stress evidence to the
previously verified native controller and ordered combat events.
Missing endpoints, a frozen clock, a stopped service, a stalled buffer
queue or contradictory statistics produce an explicit INCONCLUSIVE
result, even if the earlier shorter gameplay test was successful.

Passing this guest-side workload establishes only consistency of the
audio adapter and its bounded admission policy for this trial. It does
not prove that the host virtual sink or physical Switch speakers heard
every sound, that no audio buffer underrun occurred (skipped counters
are reported), that real-time wall-clock scheduling was sustained, or
that the original commercial arcade game was executed. A successful
900-tick count is simulation progress rather than 15 seconds measured
by external timing equipment.


## Stage 138 — identify reasons for skipped PCM admissions

Two independent NeXium trials of the preceding 900-tick test skipped
121/900 and 126/900 generated PCM blocks even though the queue remained
internally consistent and added no audout errors. These are genuine
**device-admission omissions**, not necessarily observed audio glitches
on physical speakers. Increasing the pending-page limit could hide the
symptom at the cost of more queued sound, so this stage leaves the
maximum pending pages **unchanged at two**.

The ROM-free libnx sound adapter now maintains four diagnostic-only
counters for its *existing* admission decision: skips because the
two-page queue is full; skips because the backend is inactive; skips
because the queue claims capacity but cannot find an available page;
and the maximum consecutive skip streak since the audio backend
started. These counters do not change synthesis, page ownership or
allocation. They reset together with queue accounting on successful
audout initialization.

The same native NeXium NRO stress test appends those four values at
every one of its seven guest-written checkpoints. A revised
fail-closed verifier checks that reason counts sum to the already
observed total skipped blocks, advance monotonically, never exceed
their logical bounds and do not conceal an inactive backend or
unexpected page exhaustion between checkpoints. It also reports the
six separate 150-tick skip counts so a burst can be distinguished
from evenly distributed skips. The guest-owned ordered HID witness
remains mandatory.

This instrumentation is not a fix for missing buffers. Real console
performance, perceptual audio continuity and wall-clock real-time
scheduling remain unverified. No ROMs or waveform assets are uploaded.

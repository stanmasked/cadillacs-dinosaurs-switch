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

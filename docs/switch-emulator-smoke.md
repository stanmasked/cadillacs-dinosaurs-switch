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

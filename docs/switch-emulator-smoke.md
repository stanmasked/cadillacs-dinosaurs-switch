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
  --runtime 10
```

For custom launcher arguments, repeat `--emulator-arg OPTION` before
the NRO. The probe deliberately **does not** install emulators,
download keys or firmware, read private emulator configuration, or
collect full emulator logs. It will terminate its direct child process
after the bounded interval. Do not run it against an existing shared
emulator session with unsaved work.

Possible machine results are `INVALID_NRO`,
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

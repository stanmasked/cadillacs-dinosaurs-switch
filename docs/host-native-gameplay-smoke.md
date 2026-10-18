# ROM-free native C gameplay preview (stage 124)

This is a usable **desktop gameplay preview** that runs the **same C
simulation and SFX synthesizer** used by the Switch NRO, independent
of Switch services. Unlike a process-liveness check, it really executes
movement, jump, hit, combo, enemy pursuit and synthetic audio math.

It is **not** emulation of ARM64 Switch code, libnx framebuffer,
controller/IPC or the audout driver. Its rendered 384×224 RGB image
is a new standalone geometric drawing created for test visualization,
not a captured Nintendo Switch/MAME frame.

## Play with a keyboard

Install a C11-capable GCC compiler and Python 3 with the standard
`tkinter` module. No ROM, game assets, sound files, Nintendo firmware,
keys, SDL or commercial emulator is required.

```sh
python3 tools/dino_host_preview.py
```

The window is 768×448 (2× pixel-doubled visualization) and includes
the training-room actor and opponent.

| Desktop key | Action |
| --- | --- |
| Arrows / WASD | Move across and along the depth lanes |
| J | Single punch; three successful hits trigger an invented finisher |
| K | Jump |
| L | Toggle the self-authored sparring AI |
| R | Reset |
| Escape | Exit |

The host preview **does not play sound** through desktop speakers:
it evaluates every actual C SFX sample and maintains a cumulative,
deterministic PCM checksum. Optional separately authored sounds can
be heard using `tools/dino_sfx_preview.py`.

## Deterministic headless scenario + original test frame

```sh
python3 tools/dino_host_preview.py --headless --ticks 180 \
  --out-frame /your/private/folder/dino-training-room.ppm
```

The scenario drives real C code with 70 movement ticks, three
confirmed practice hits, toggle sparring, another attack and a jump.
No Python reimplementation of physics is used. A generated PPM is
an original, ROM-free rasterization of the resulting state, not
an emulated framebuffer capture. Existing frame output is never
overwritten. The JSON report includes ticks, coordinates, player/
opponent HP, hits, combo, pose-independent frame SHA-256 and
sample-for-sample FNV64 for 48kHz stereo PCM output.

A bounded `--ticks` integer from 1 to 3600 is accepted; custom
frames outside the original scenario can be used to test idle states.

GitHub Actions' **Native ROM-free gameplay visual smoke** workflow
executes nine standalone integration tests, renders a reference
`training-room.ppm`, validates its hash against the native C
output, and publishes only the independently drawn PPM and
`host-witness.json` in a 7-day short-lived artifact. It does not
publish an original game's ROM or screenshot.

There are three independent evidence levels:

1. A Switch NRO compiles (cross-toolchain build, no execution).
2. Portable C gameplay and audio **execute** in the desktop
   preview (real game-code execution, but not Switch emulation).
3. A Switch emulator displays the actual NRO's game frames and
   accepts input/audio (still **not confirmed** in current environment).

This distinction remains explicit in every machine JSON report:
`switch_emulator_verified`, `switch_gpu_verified` and
`switch_audio_verified` are always `false` in host-preview mode.

For an actual emulator, use the separate
[Switch emulator launch and visual QA guide](switch-emulator-smoke.md)
with user-installed, authorized software. Never publish private keys,
commercial firmware or original game image data.

## Stage 125 — real desktop window and keyboard smoke with Xvfb

The native-host visual workflow additionally boots an actual **Tk**
window in a virtual X11 display, sends genuine Tk key-press/release
events (arrow movement and a punch), advances the **same portable C
game and sound engines**, presents a 2× `PhotoImage` in a live Canvas,
and reads back known player/opponent RGB pixels from that Tk image.
It reports a separate `tk-gui-witness.json` containing
`tk_image_rendered`, `held_input_verified`,
`edge_input_verified`, a 768×448 preview size, nine ticks and
a final player X position of 98. The report has an explicit
`runtime: tk_desktop_not_switch_emulator` marker and leaves all
Switch emulator, Switch GPU and Switch audio proof flags **false**.

The desktop interactive mode also now uses a fixed **60Hz simulation
clock**, independent of the Tk frame rendering schedule; it is no
longer tied to a naive 16 ms repaint interval (62.5 Hz).
A desktop stall limits catch-up to eight simulation ticks per
render to avoid an unbounded backlog; unusually late ticks
are counted as dropped by the local scheduler. Input presses
persist through redraws until consumed by an actual game tick.
Separately authored tests verify held-direction input,
attack edge suppression of auto-repeat, 60Hz fractional-tick
accuracy and the bounded catch-up policy.

To perform a GUI-only smoke on Linux with the necessary X11/Tk
packages installed:

```sh
xvfb-run -a python3 tools/dino_host_preview.py --gui-smoke
```

No Nintendo Switch emulator, keys, firmware, game ROMs or protected
assets are used by this Linux desktop verification. Testing the
**actual NRO in an actual Switch emulator** remains a distinct
uncompleted task, not a claim implied by a successful Tk window.

## Stage 126 — a single replay trace inside both NRO and desktop execution

`source/dino_replay.c` is now the **one** source of the invented
180-tick controller script previously duplicated in Python.
The native-host dynamic library compiles the same C replay module as
the Nintendo Switch NRO; the headless preview calls it directly.
Its final local expectation is **x=230, three confirmed hits,
player HP 4, sparring ON** after 180 fixed 60Hz steps, with no
original graphics, game ROM or emulator requirement.

The Switch training-room UI has a new **Minus** action to start or
restart this self-contained test. The same 180 scripted input steps
update the real Switch training game objects, through exactly the
same `dino_arena_step()` and combat-event SFX path as controller
play. It freezes the final frame instead of continuing AI,
and overlays `C REPLAY 180/180 DONE - Y RESET HP 4 HITS 3`.
Use **Y** to return to normal play, or **Minus** to replay.

Five new host-native tests check the 180-tick bounds and pointer
safety, button-mask validity, exact frame numbers of individual
inputs, parity between calling the C replay API directly and
calling the desktop preview's replay bridge, final player/enemy
state and PCM identity, and harmless out-of-range replay calls.
The dedicated native gameplay workflow now triggers on modifications
to the replay source and executes these exact tests.

When an emulator becomes available, observing the **actual Switch
NRO** finish this scripted scenario will be a meaningful first
runtime test. Until then, any success statement here applies only
to the compiled NRO and independently executed **host** C code,
not to Switch emulator GPU, controller or audout behavior.

## Stage 127 — independent cross-platform replay fingerprint

`tools/dino_host_preview.py --headless --ticks 180` now includes a
`gameplay_witness_fnv64` field: exactly 16 lowercase hexadecimal digits.
This is the **same per-tick C witness algorithm** and input sequence
compiled into the Switch NRO, so a later actual emulator test can
compare it against the `STATE FNV64` line on the frozen on-device
frame. The hash includes selected game state and event flags for all
180 simulation ticks, but no host PCM bytes or renderer pixels.

The portable C witness is independently checked against a Python
reference that feeds each integer field as four explicit little-endian
bytes to FNV-1a. Tests also ensure a missed move/attack/jump alters
the final digest, repeated reset/replay produces the same result
and null input does not modify the digest. This is intended to
detect **real simulation divergence** across platforms, not to
claim real emulator execution from a host-only result.

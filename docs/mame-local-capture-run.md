# Stage 26 — one-command local instrumented MAME capture

This optional helper closes the operational gap between checked
original game ROMs and the same-render-pass MAME frame exporter.

It does **not** emulate the game, reconstruct gameplay, download
ROMs or establish that the native Switch renderer matches MAME.
It must be used with **your own locally built, instrumented MAME**
(see [render-pass capture](mame-render-pass-capture.md), PR #8).

## Prerequisites and local installation

Place your privately owned MAME game set and separately obtained device
set in a local ROM directory (do **not** upload them to GitHub):

```text
/private/mame-roms/
    dino.zip
    qsound_hle.zip
```

MAME's QSound HLE device references `dl-1425.bin` with expected
length 8192 bytes and CRC32 `d6cf5ef5`; this is not part of the
game ZIP and must be obtained/verified separately. The parent ROM
preflight PR #12 checks this dependency and the 16 essential game
ROM images without redistributing any of their contents.

The MAME executable must include the optional
`tools/mame_render_instrument.py` source patch and be executable
on your local operating system. A normal installed MAME will run
the game but **will not generate the extra capture files**.

## Readiness-only check

```sh
python3 tools/mame_local_capture_run.py \
  --mame /path/to/instrumented/mame \
  --rom-dir /private/mame-roms \
  --capture-dir /private/cps1-capture \
  --start 900 --count 6 \
  --probe-only \
  --report /private/cps1-preflight-report.json
```

This verifies the core game ROM ZIP and QSound device ZIP, then runs
`mame -version` and `mame dino -rompath ... -verifyroms`.
It does **not** launch the game or create a capture folder in
`--probe-only` mode.

To let the emulator itself decide when a device ZIP is unavailable,
use `--allow-unverified-device`. This relaxes only our own
early device precheck; **MAME `-verifyroms` must still succeed**.

## Record and replay input to reach the FIRST level

An unattended MAME session may remain on attract-mode screens. To
capture the real first level, first record a **private controller input**
session using the *same* emulator version, ROM revision and settings
as the capture run. On a host where you can launch MAME interactively:

```sh
/path/to/mame dino -rompath /private/mame-roms \
  -record /private/first-stage.inp
```

Play through startup, insert a virtual coin and start the game, then
move into the first level before stopping the recording. Treat the
recorded `.inp` as a user-private input timeline; do not check it
into GitHub. This recording is **not provided** by the project.

Pass it to the instrumented capture runner:

```sh
python3 tools/mame_local_capture_run.py \
  --mame /path/to/instrumented/mame \
  --rom-dir /private/mame-roms \
  --capture-dir /private/first-stage-render \
  --start 900 --count 6 \
  --seconds-to-run 40 \
  --playback-inp /private/first-stage.inp \
  --report /private/first-stage-run-report.json
```

The `--start` frame must be determined for **that particular recording**
and the input recording must last long enough to reach it. The runner
does not claim that frame 900 is actually first-level gameplay.

The runner checks that the recorded input is a nonempty, regular
`.inp` file no larger than 64 MiB and passes the file to MAME using
the **`-playback` option without invoking a command shell**. It records
only the file length and SHA-256 in the JSON report. It rehashes the
recording after the emulator exits and **rejects a capture if those
bytes changed during execution**.

Reproducibility is conditional. MAME warns that playback can
desynchronize if its configuration, NVRAM or memory-card data differ.
Use a matching emulator version and identical configuration; do not
assume a syntactically valid .inp produces the same game state.
The provenance report therefore always marks
`input_replay_verified: false`. Only inspecting actual captured
render frames can establish that the first level was entered.

Official MAME documentation:
https://docs.mamedev.org/commandline/commandline-all.html

## Capture complete frames

```sh
python3 tools/mame_local_capture_run.py \
  --mame /path/to/instrumented/mame \
  --rom-dir /private/mame-roms \
  --capture-dir /private/cps1-capture \
  --start 900 --count 6 \
  --seconds-to-run 30 --wall-timeout 300 \
  --report /private/cps1-run-report.json
```

MAME's `-seconds_to_run` bounds emulated running time; the Python
`--wall-timeout` also limits actual elapsed process execution.
`-nothrottle` can improve throughput on hosts that support it.

The script never uses a shell, overwrites existing reports or
captures into a nonempty directory, and sets three explicit
environment variables for the instrumentation:
`CPS1_RENDER_DUMP_DIR`, `CPS1_RENDER_DUMP_START`, and
`CPS1_RENDER_DUMP_COUNT`.

If the game does not reach the selected rendering frames, or MAME
performs only partial raster updates instead of a complete viewport,
capture validation fails. In that case **no valid first-level frame
has been demonstrated**; review game input, startup delay, MAME video
callback behavior and capture hook. The diagnostic report is produced
only for fully valid sets; partial files remain local to inspect.

When all six binary streams for each requested frame are present,
the runner checks their exact sizes, manifest contract, original
screen dimensions, same-render callback provenance and SHA-256.

**Important:** the collected JSON records what an external binary
reported. It cannot authenticate that binary as unmodified upstream
MAME. Even on success, flags remain `pixel_parity_verified=false`,
`gameplay_reconstructed=false` and
`native_switch_runtime_tested=false`.

## Send verified-format captures to the Switch viewer

Once actual captures exist and PR #11 is available:

```sh
python3 tools/mame_capture_sequence.py /private/cps1-capture \
  --first-frame 900 --count 6 --fps 60 \
  --out-dir /private/dino-native-sequence
```

Copy the resulting **private** `sequence.bin` to the existing native
Switch v0.5 viewer folder. Do not upload captured graphics, memory,
ROMs or private sequences to GitHub.

## ROM-free tests

```sh
python3 -m unittest discover -s tests -p 'test_mame_local_capture_run.py' -v
```

The 15 runner regression cases run a tiny Python **test stand-in**, not
real MAME. They cover private INP playback, unexpected INP changes, success, readiness-only mode, missing QSound,
invalid core ROM, missing binary, false same-pass manifest,
truncated VBlank OBJ, invalid ranges, failed `-verifyroms`,
no-overwrite safety and CLI status.

The actual game/first stage is unverified until real MAME successfully
boots and produces authentic complete render-pass data.

MAME documentation:
https://docs.mamedev.org/commandline/commandline-all.html

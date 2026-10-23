# Stage333 — private Wine launcher for MAME 0.106

## Purpose

The existing private gate and capture tools expect one executable path and pass MAME arguments directly. This launcher adapts that interface to a local Wine installation without changing the audited Python tools.

The launcher is generic and contains no game data. It refuses a MAME executable or Wine prefix inside the repository, refuses a symlink as the MAME executable, and does not print recording paths or game output itself. The existing gate/capture tools keep their bounded timeouts and private-only output handling.

## Runtime requirements

Use a Linux host with working 32-bit Wine support, or an equivalent trusted environment that can run Wine32 and its child processes. The previous container could start the Wine ELF through QEMU but could not run Wine's re-executed 32-bit loader; that environment is **not** suitable for the real replay test.

Use the pinned technical MAME 0.106 artifact from Stage329. This build has the MNG count-trace instrumentation used by the private capture tool. It is a source-pinned MAME build, **not an authenticated WolfMAME binary**. A successful run remains candidate evidence until the recording, frame counts and traces are independently audited.

Keep the original dino.zip, dino.inp, and dino.wlf on the private host. Do not upload them to GitHub, attach them to Actions, or place them under the repository checkout. Keep all MNG/CSV output and JSON receipts in a private directory as well.

## Setup

From the repository checkout, create a private working directory outside it. Put the verified mame0106.exe and the original ROM/recording files in separate private subdirectories. Use a fresh Wine prefix that does not already exist and ensure its parent directory exists.

Example paths below are placeholders; replace them with actual absolute local paths, never with repository paths:

    chmod +x tools/wolfmame0106_private_wine_launcher.sh
    export MAME0106_EXE=/private/cadillacs/mame/mame0106.exe
    export WINE_BIN=wine
    export WINEPREFIX=/private/cadillacs/wine-prefix
    mkdir -p /private/cadillacs

The launcher sets WINEARCH=win32 when Wine initializes the prefix. Do not reuse an existing 64-bit prefix. It validates that the MAME executable and prefix are outside the repository before forwarding any arguments.

## Gate first — do not skip

Run the existing private read-only gate:

    python3 tools/wolfmame0106_private_binary_gate.py \
      --emulator "$PWD/tools/wolfmame0106_private_wine_launcher.sh" \
      --rom-dir /private/cadillacs/roms \
      --inp /private/cadillacs/recording/dino.inp \
      --wlf /private/cadillacs/recording/dino.wlf \
      --out /private/cadillacs/audits/stage333-gate.json

The gate checks the INP/WLF pair, MAME 0.106 help output, and -verifyroms dino. It does not run gameplay. Continue only if the report status is READY_FOR_MANUAL_PRIVATE_INP_PLAYBACK_NOT_VERIFIED and dino_rom_verifyroms_passed is true. A failure must remain a failure; do not change the ROM verifier's accepted output just to get past the gate.

## Bounded 121-frame candidate capture

Only after the gate passes, run the already audited private capture utility:

    python3 tools/wolfmame0106_private_mng_capture.py \
      --emulator "$PWD/tools/wolfmame0106_private_wine_launcher.sh" \
      --rom-dir /private/cadillacs/roms \
      --inp /private/cadillacs/recording/dino.inp \
      --wlf /private/cadillacs/recording/dino.wlf \
      --frames 121 --start-frame 0 --seconds 180 \
      --capture-out /private/cadillacs/captures/stage333-0000.mng \
      --trace-out /private/cadillacs/traces/stage333-0000.csv \
      --out /private/cadillacs/audits/stage333-capture.json

Ensure the parent directories for receipts, captures and traces already exist. The tools use exclusive private outputs and must not overwrite existing evidence. A process exit code of zero alone is not sufficient.

## Acceptance criteria

- The private gate verifies dino.zip against the pinned dino driver.
- The capture report requests exactly 121 frames and validates an MNG with exactly 121 embedded PNG frames.
- MNG/PNG dimensions, chunk CRCs, PNG scanlines, frame boundaries and end marker pass the existing audit.
- The optional count trace exists, is bounded, has contiguous callback frames and changing counters; then run the existing Stage290 trace audit and Stage291 dual-run overlap audit before claiming counter consistency.
- Keep the original input, ROM, captures, traces and their hashes outside the public repository. Publish only aggregate pass/fail status and stage documentation.
- Even after all these checks, label the result as unauthenticated candidate replay until the emulator provenance and INP-to-video alignment are independently established. The current workflow must not claim original-game parity or Nintendo Switch parity.

## ROM-free CI

The Stage333 workflow tests this exact launcher with the source-pinned MAME artifact using only -help, -showconfig, and -listxml. It also verifies that the launcher refuses a repository-local executable path. No ROM, INP/WLF, MNG or gameplay trace is staged in public CI.

# Stage295 — real MAME 0.106, synthetic Z80 diagnostic

## Why this test matters

Stages 290–294 verified source patches, built the historical Windows MAME
executable, tested synthetic MNG parsers, and exercised two child processes
through a **Python imitation of MAME**. They did not prove the historical
emulator itself can load a game, execute a CPU, or record input and MNG.

Stage295 adds a **separate ROM-free-from-the-user real emulator probe** to
the historical Windows GitHub Actions job. It uses a completely original
synthetic Z80 program, not the user's original ROM, recorded input or game
graphics.

The pinned historical MAME 0.106 tree already contains a small `minivadr`
(Minivader) Z80 hardware driver with an 8 KiB program ROM.
A new source-anchored tool generates 8,192 synthetic bytes consisting of a
tiny Z80 loop that writes changing values to mapped video RAM and
otherwise contains zeros. The tool then patches **only the checksum
expectations** in a disposable copy of upstream
`src/drivers/minivadr.c`. All upstream game-source edits are
made **after** the standard production MAME executable has already been
built, copied, checked and uploaded as a code-only artifact.

No original copyrighted ROM is present, generated, extracted, copied, or
uploaded. The generator merely creates source-independent artificial CPU
instructions and a byte-filled test ROM within the short-lived CI runner.

## Windows CI test protocol

After the normal historical MAME 0.106 production build and its ROM-free
artifact upload:

1. Generate artificial `minivadr/d26-01.bin` inside a short-lived
   Windows CI workspace and patch its expected SHA-1/CRC32 in the
   **test-only** driver source.
2. Recompile MAME with the synthetic driver's expected checksum.
   This recompilation must **not replace** the published production
   `runtime-artifact/mame0106.exe`.
3. Invoke the **real Windows MAME process** with
   `-verifyroms minivadr -rompath <synthetic-root>`. A positive ROM
   loader and checksum result is mandatory for the job to pass.
4. Attempt a bounded 48-frame graphical recording from the synthetic CPU
   with `-record test295` using small, explicitly configured
   non-DirectDraw window options. Windows-hosted CI may not provide an
   interactive display; this must be reported as blocked, not success.
5. If a real synthetic INP was recorded, replay **only that artificial
   recording** in the real MAME with `-mngstartframe 10`,
   `-mngframes 24` and `-mngcounttrace`, then decode the resulting
   MNG and validate its callback-indexed port read counts.
6. Emit a single restricted JSON status. Do not upload generated
   recordings, MNGs, original game assets, modified driver executable,
   synthetic Z80 ROM or raw child-process logs.

The probe deliberately separates outcomes:

- `SYNTHETIC_MINIVADER_MAME_VIDEO_AND_INPUT_READ_CONFIRMED`:
  genuine historical MAME loaded the synthetic ROM and wrote/parsed
  synthetic replay MNG frames and input-read counter traces.
- `BLOCKED_SYNTHETIC_RECORDING_WINDOW_OR_GUI`:
  ROM loader succeeded but hosted graphics/recording could not run.
- `BLOCKED_SYNTHETIC_PLAYBACK_MOVIE_OR_TRACE`:
  recording succeeded but replay could not deliver the expected files.
- `BLOCKED_SYNTHETIC_MNG_DECODING` and
  `BLOCKED_SYNTHETIC_MNG_FRAME_COUNT`: replay produced
  incomplete or invalid MNG evidence.
- `BLOCKED_SYNTHETIC_ROM_LOADER`: even the real
  emulator could not accept the artificial Z80 test ROM. This is a
  **required** CI check and makes the historical Windows job fail.

**A successful ROM-loader check is not a successful gameplay-replay test.**
The hosted-Windows GUI attempt is experimental and not a required CI
condition. No success should be claimed for input recording, video
capture, or gameplay unless the corresponding result flag is confirmed.

## Local synthetic-only checks

~~~sh
python -m unittest discover -s tests -p 'test_mame0106_synthetic_*_295.py' -v
~~~

This deliberately tests the **real 2006 MAME executable** more deeply,
but it cannot verify an original `dino.inp` replay, WolfMAME-specific
additions, or Cadillacs and Dinosaurs graphics.

Actual dino ROM/INP/WLF and derived captures must remain outside GitHub.
A future genuine private Windows experiment is still required to establish
original-game input behavior and visual parity.

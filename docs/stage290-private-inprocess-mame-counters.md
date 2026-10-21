# Stage290 — private in-process MAME INP/video counter trace

## What this measures

The code-only Windows MAME 0.106 runtime built from the pinned historical
source now supports opt-in -mngcounttrace alongside Stage286's bounded
-mngstartframe/-mngframes capture.

The source-anchored Stage290 instrumentation counts two events **inside the
same MAME process**:

1. Successful calls to the input-port playback reader for port 0
   (the first port in MAME 0.106 input_port_vblank_start).
2. All successful 32-bit port playback reads.

At each written MNG frame it appends a row containing the Stage286 zero-based
video callback index and the two cumulative counts. No controller button
state, raw INP data, pixels or ROM content is logged. This **does not** prove
that an INP record index equals a video callback index.

The instrumentation is applied only to the exact upstream mame0106 revision
after the original Stage286 windowed MNG patch. Its builder rejects changed
source contexts and retains a five-file combined reproduction patch. CI
checks the -mngcounttrace option with -showconfig without loading a ROM.
The result is custom-patched historical MAME, **not authenticated WolfMAME**.

## Private use

On a private Windows workstation with an authorized dino ROM, the paired
original INP/WLF and the Stage290 MAME executable, request a private
MNG, trace and exclusive JSON receipt:

~~~bat
python tools\wolfmame0106_private_mng_capture.py ^
  --emulator C:\private\mame0106.exe ^
  --rom-dir C:\private\roms ^
  --inp C:\private\recordings\dino.inp ^
  --wlf C:\private\recordings\dino.wlf ^
  --start-frame 36000 --frames 1200 --seconds 1800 ^
  --capture-out C:\private\audits\window-a.mng ^
  --trace-out C:\private\audits\window-a-counts.csv ^
  --out C:\private\audits\window-a.json
~~~

The runner uses an isolated private temporary directory and suppresses
emulator stdout/stderr. When --trace-out is set, it opts into the new flag.
A missing/oversized trace blocks the capture. Both MNG and count trace bytes
are SHA-256-bound to the private receipt. Do not upload these three files.

For a successful capture, verify the MNG, receipt and trace:

~~~bat
python tools\wolfmame0106_private_count_trace.py ^
  --mng C:\private\audits\window-a.mng ^
  --trace C:\private\audits\window-a-counts.csv ^
  --capture-receipt C:\private\audits\window-a.json ^
  --out C:\private\audits\stage290-audit.json
~~~

The validator requires valid private trace and MNG file hashes, exactly
the requested number of sequential video callbacks, valid MNG/PNG structure
and monotone INP-reading counters. Its derived, exclusive private JSON
report includes only aggregates and explicit false provenance flags:
no private paths, per-frame data, input values, hashes or images.

**Critical evidence boundary:** first_port_reads counts successful port-0
reads, not independently authenticated WolfMAME INP records. Initialization,
video callback scheduling, analog-port reads and skipped rendering can
affect the offset. callback_index minus first_port_reads is an exploratory
counter difference, **not verified controller latency or video/input
synchronization**. A structurally valid trace does not prove original game
playback or Nintendo Switch gameplay parity.

## ROM-free CI

~~~sh
python -m unittest discover -s tests -p 'test_wolfmame0106_private_count_trace.py' -v
python -m unittest discover -s tests -p 'test_wolfmame0106_private_mng_capture.py' -v
~~~

Tests use tiny synthetic MNGs, count traces and private receipt placeholders.
The Windows build checks source compilation and option presence only.
Real original-game playback, WolfMAME binary provenance and physical Nintendo
Switch testing remain unverified.

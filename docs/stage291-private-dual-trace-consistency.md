# Stage291 — cross-run private pixel and input-counter consistency

Stage291 compares **two sets of files** from separate private Stage290
capture requests:

- first MNG, its signed-by-nobody but SHA-bound local capture receipt,
  and its retained Stage290 input-read count CSV;
- second MNG, private capture receipt and count CSV.

No source ROM, INP, WLF, original game video or raw controller signal is
included in the public repository. All six evidence files must be private
ordinary files outside the Git repository.

## Purpose and evidence boundaries

Stages 287–288 compared **normalized pixels** in overlapping candidate
video windows. Stage290 counted successful input port reads and output video
callbacks **inside a single patched historical MAME 0.106 process**.

Stage291 tests whether *both* streams agree at corresponding requested
callback indices in two candidate captures. In addition to pixel equality it
compares port-0 read counts and total successfully read 32-bit playback words.
Those counters are metadata about the instrumented MAME process, **not**
a guarantee of correct controller input, authentic WolfMAME provenance or
exact video-to-INP record alignment.

## Capture setup

Generate two fresh private Stage290 windows with **different start indices
but a real overlap**. Both must use the same local original INP/WLF,
and each must retain an MNG, count CSV and Stage290 capture receipt:

~~~bat
python tools\wolfmame0106_private_mng_capture.py ^
  --emulator C:\private\mame0106.exe --rom-dir C:\private\roms ^
  --inp C:\private\recordings\dino.inp ^
  --wlf C:\private\recordings\dino.wlf ^
  --start-frame 36000 --frames 1200 --seconds 1800 ^
  --capture-out C:\private\audits\window-a.mng ^
  --trace-out C:\private\audits\window-a-counts.csv ^
  --out C:\private\audits\window-a.json

python tools\wolfmame0106_private_mng_capture.py ^
  --emulator C:\private\mame0106.exe --rom-dir C:\private\roms ^
  --inp C:\private\recordings\dino.inp ^
  --wlf C:\private\recordings\dino.wlf ^
  --start-frame 36600 --frames 1200 --seconds 1800 ^
  --capture-out C:\private\audits\window-b.mng ^
  --trace-out C:\private\audits\window-b-counts.csv ^
  --out C:\private\audits\window-b.json
~~~

These examples yield 600 overlapping video callbacks, provided both runs
finish cleanly and write all requested frames. Use the fresh Stage289 or
later receipts: legacy receipts missing INP/WLF SHA-256 are rejected.

## Run the private comparison

~~~bat
python tools\wolfmame0106_private_dual_trace_consistency.py ^
  --first-mng C:\private\audits\window-a.mng ^
  --first-receipt C:\private\audits\window-a.json ^
  --first-trace C:\private\audits\window-a-counts.csv ^
  --second-mng C:\private\audits\window-b.mng ^
  --second-receipt C:\private\audits\window-b.json ^
  --second-trace C:\private\audits\window-b-counts.csv ^
  --min-overlap 16 ^
  --out C:\private\audits\stage291-dual-overlap.json
~~~

The comparator performs, in order:

1. Require **distinct** videos, capture receipts and count traces and
   matching, structurally valid **private** INP/WLF content SHA-256 values
   in both local receipts (without exporting those values).
2. Re-run both Stage290 MNG/trace audits and the Stage288 normalized-pixel
   overlap check. No successful pixel overlap means no positive counter
   result.
3. Compare aligned **integer** port-0 and total-playback-word counts for
   all common callback indices, recording aggregate matches, divergence
   counts and first mismatching callback index only.
4. Repeat count-trace validation after the comparison to detect ordinary
   file changes while reading. The final report never contains paths,
   file hashes, full counter rows, input values or images.

Statuses:

- PIXELS_AND_INPUT_READ_COUNTERS_MATCH_UNAUTHENTICATED: dynamic pixel
  and dynamic input counter sequences match in the compared region.
- PIXELS_MATCH_INPUT_READ_COUNTERS_DIVERGE_UNAUTHENTICATED:
  corresponding video pixels agree but some input counters differ.
- PIXELS_MATCH_COUNTERS_STATIC_IN_OVERLAP_UNAUTHENTICATED:
  matched pixels but the input counters are unchanged throughout the
  overlap, which is weak evidence.
- BLOCKED_CANDIDATE_PIXEL_OVERLAP_NOT_DYNAMIC_MATCH:
  video regions are incomparable, static or pixel-inconsistent.
- BLOCKED_PRIVATE_DUAL_CAPTURE_AUDIT:
  file integrity, private input binding, receipt or trace checks failed.

Only the first status returns exit code zero. All other statuses return 2.
Derived JSON reports must remain private during development.

**Strict limit:** even full agreement merely demonstrates consistency of
the two *supplied candidate* recordings and their **unauthenticated** local
counter traces. It cannot attest independent emulator executions or prove
that original INP record 36,000 corresponds to video callback 36,000. These
are still different counters and require separate causal verification.

## Public synthetic checks

~~~sh
python -m unittest discover -s tests -p 'test_wolfmame0106_private_dual_trace_consistency.py' -v
~~~

All test MNG frames and counter rows are artificial. No original game
assets are required and no private recordings are uploaded to CI.

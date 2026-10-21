# Stage292 — one-command private two-window MAME experiment

Stage292 adds a **local-only** coordinator over the already tested Stage286
bounded capture, Stage290 in-process input-read counters and Stage291
cross-capture consistency auditor.

The coordinator does **not** run in GitHub Actions with an original ROM, INP,
WLF, private MNG, or video capture. Public CI uses miniature **synthetic**
MNG frames and synthetic unsigned receipt values only.

## Local command

Use the custom-patched, ROM-free Windows MAME 0.106 executable from the
successful Stage290 build, paired private dino INP/WLF, and authorized private
ROM directory. Choose an **entirely new private output folder** beneath a
private existing parent directory, never under the cloned GitHub repository.

~~~bat
python tools\wolfmame0106_private_two_window_experiment.py ^
  --emulator C:\private\mame0106.exe ^
  --rom-dir C:\private\roms ^
  --inp C:\private\recordings\dino.inp ^
  --wlf C:\private\recordings\dino.wlf ^
  --out-dir C:\private\audits\experiment-001 ^
  --first-start 36000 --frames 1200 --shift 600 --seconds 1800
~~~

The tool validates the recording's structural length, chooses the first
callback window [36000, 37200) and the second [36600, 37800), then checks
that both are inside the recorded input length **as a conservative
precondition, not proof of record/callback correspondence**. Both windows
have 1,200 callbacks and a requested overlap of 600 callbacks.

It creates the new private directory, runs the first capture to completion,
writes an exclusive private receipt, then runs the second. If a capture
fails, it stops before starting a following run; private evidence from
attempted runs stays inside the private directory. It does not overwrite
an existing experiment directory.

On two clean complete candidate captures, it executes the Stage291 auditor:
both MNGs and counter traces must match their local receipt SHA-256s, share
the same INP/WLF source fingerprints, contain dynamic equal video pixels in
the callback overlap, and have equal, changing input-read counters at each
of those overlapping callback indices.

## Private files

A successful experiment directory contains seven **private** files:

- first.mng / first-counts.csv / first-receipt.json
- second.mng / second-counts.csv / second-receipt.json
- stage292-summary.json

The stage292-summary.json contains only bounded frame/count statistics,
status labels and explicit false provenance/alignment flags. It omits
original recording bytes, button details, screenshots, paths and hashes.
It is written with exclusive creation and restrictive permissions.
All seven files **must stay outside GitHub**, including branch commits,
Issues, PR attachments and CI artifacts.

## Outcomes

- TWO_CAPTURE_PIXEL_AND_COUNT_CONSISTENCY_CANDIDATE_ONLY (exit 0):
  two *supplied candidate runs* produced matching changing MNG pixels
  and matching changing read counters in the requested overlap.
- TWO_CAPTURE_CANDIDATES_NOT_CONSISTENT (exit 2):
  a comparison finished but found a mismatch, static evidence or
  incomplete candidate consistency.
- BLOCKED_FIRST_PRIVATE_CAPTURE / BLOCKED_SECOND_PRIVATE_CAPTURE:
  capture was incomplete, timed out, had nonzero exit or was missing
  its privately retained video or trace.
- BLOCKED_PRIVATE_DUAL_COMPARISON / BLOCKED_PRIVATE_EXPERIMENT_SETUP:
  malformed, unsafe or missing local evidence, incorrect window
  parameters or another failure prevented a trustworthy comparison.

The first-window start, per-window frame count, second-window shift and
hard process timeout are bounded. Each window is at most 3,601 frames and
the shift and intersection must be at least 16 frames. The program does
not automatically upload, delete, repair or re-run private evidence files.

**Critical:** a zero exit still does not independently authenticate
WolfMAME binary provenance, original INP playback, two genuinely independent
runs, input/video causal alignment, game pixel parity or operation on a
physical Nintendo Switch. It only confirms two candidate data sets satisfy
the bounded structural consistency conditions. Original ROM/INP/WLF must
never be publicly uploaded or included in logs.

## CI

~~~sh
python -m unittest discover -s tests -p 'test_wolfmame0106_private_two_window_experiment.py' -v
~~~

The synthetic tests cover complete dual runs, first/second capture failure,
pixel mismatch, input counter mismatch, invalid window lengths, existing
folder protection, symlinked parent rejection, an exception hiding sensitive
path details and sanitized status reports. The public build checks only
code integrity and Nintendo Switch bootstrap compilation.

## After this

The meaningful next step requires a **private machine capable of running
the original ROM with the user-provided INP/WLF in the instrumented MAME**.
Until that is executed, neither input/video causal alignment nor original
arcade gameplay parity is confirmed. Retain the PR in Draft.

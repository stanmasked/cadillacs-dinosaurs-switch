# Stage285 — private, bounded INP playback plus MNG capture

Stage284's MNG validator has passed synthetic CI. Stage285 adds a private
runner that connects the existing read-only binary/ROM/INP/WLF preflight
to a bounded capture attempt.

## Required private workstation inputs

Keep these outside the public repository:

- Historical MAME 0.106 or compatible WolfMAME 0.106 executable.
- Authorized ROM directory containing the expected dino ROM set.
- Paired original dino.inp and dino.wlf files.

The runner calls the Stage279 gate first. It refuses to start if the
recording isn't identified as the WolfMAME 0.106 family, the emulator's
help does not report MAME 0.106, or the ROM verification fails. The
upstream MAME build from Stage283 is **not** attested as WolfMAME.

## Bounded capture command

On the private Windows workstation, from a Python environment containing
the repository's tools:

    python tools/wolfmame0106_private_mng_capture.py ^
      --emulator C:\private\mame0106.exe ^
      --rom-dir C:\private\roms ^
      --inp C:\private\recordings\dino.inp ^
      --wlf C:\private\recordings\dino.wlf ^
      --frames 121 --seconds 120 ^
      --capture-out C:\private\audits\stage285.mng ^
      --out C:\private\audits\stage285.json

The runner copies the input pair byte-for-byte into a temporary private
workspace, creates a private MNG output directory, and explicitly sets
-mng_directory to that directory. It runs the dino playback command with
-frames_to_run 121 and -mngwrite stage285. Historical MAME 0.106 appends
the .mng extension and uses the configured MNG directory, so the runner
audits mng/stage285.mng before optional private retention. The working
directory is temporary and removed after the run.
The raw emulator stdout/stderr are discarded; the report does not contain
private paths, raw frames or input events. The report file is exclusive,
private, and mode 0600. The optional MNG output is also exclusive and mode
0600, and must be outside the repository.

The run limit and process timeout are bounded. -frames_to_run 121 is a
request to the emulator, **not** proof that 121 recorded input records were
consumed. A valid MNG proves only that a candidate stream contains well-formed
image frames with measurable pixel continuity.

## Evidence semantics

The runner reports separate facts for:
- the read-only recording/version/ROM preflight;
- whether the process spawned, exited zero, or timed out;
- whether a candidate MNG exists and passes the independent structural and
  decoded-pixel audit;
- candidate frame count and adjacent identical/changed frame pairs.

Even CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED is deliberately not
called a successful original replay. It does **not** prove the executable
is WolfMAME, the original INP played to completion, the video is aligned
to input records, original gameplay matches, or a physical Switch was tested.

## ROM-free tests

    python -m unittest discover -s tests -p 'test_wolfmame0106_private_mng_capture.py' -v

Tests use artificial input placeholders and tiny synthetic RGB MNG files.
No copyrighted game assets or actual input recordings are needed or allowed
in public CI. This PR stacks on Stage284 and changes neither main nor
approved cover assets.

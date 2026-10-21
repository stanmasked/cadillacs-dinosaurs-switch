# Stage293 — ROM-free real-subprocess smoke test of private capture pipeline

Stage293 verifies the integration boundary between the Stage292
orchestrator and the Stage286/290 **actual** subprocess runner.
Previous orchestration tests used fake Python callbacks; the new
regression suite executes a **real separate executable** through the
same isolated workspace, process launcher, MNG audit, count-trace
retention and Stage291 comparison used by the private project.

The executable is an **artificial Python stand-in**, not MAME or dino.
It generates only synthetic 2x2-pixel MNG frames and fake cumulative
input-read counters. Original ROM validation and original INP/WLF
metadata checks are stubbed in these tests. There is no genuine game
playback or source WolfMAME authenticity check in the synthetic CI.

## Checks

- The fake process checks required historical MAME command-line options,
  frame bounds and the explicit opt-in counter-trace flag.
- Two distinct child processes emit candidate MNG and count CSV files
  into private temporary directories.
- The real Python capture code audits those MNG containers and retains
  candidate files through exclusive, private content-bound receipts.
- The genuine Stage291 Python comparator compares byte-level output
  from the separate synthetic subprocesses.
- Missing MNG, missing CSV, malformed MNG, nonzero exit and a single
  divergent input counter fail closed.
- The final report carries aggregate counters only, with no input data,
  user paths, images or content hashes.

## Public test command

    python -m unittest discover -s tests -p 'test_wolfmame0106_subprocess_experiment_smoke.py' -v

The separate ROM-free Windows MAME build was verified at Stage290.
The present synthetic smoke tests demonstrate subprocess integration,
not playback of the original game by MAME itself.

## Next genuine-evidence gate

Running Stage292 on original dino INP/WLF and ROM requires a private
machine with locally accessible authorized original files and the
source-pinned, instrumented Windows MAME executable. Keep its resulting
MNGs, CSVs, source files, hashes, private receipts and screenshots
outside GitHub, including Actions and PR attachments. Matching synthetic
or even matching private candidate counters is not proof of exact input
record/video callback mapping, original game parity or physical Nintendo
Switch execution.

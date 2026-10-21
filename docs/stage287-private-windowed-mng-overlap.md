# Stage287 — private decoded-pixel repeatability audit

Stage286 supports bounded video-callback MNG capture from a **custom-patched,
source-pinned upstream MAME 0.106** executable. This stage checks whether two
candidate MNG windows have identical **decoded pixels** at shared candidate
video indices. This can reveal inconsistent captures, but it **does not prove**
independent executions, authentic WolfMAME provenance, correct INP playback,
input/video synchronization, gameplay parity, or execution on physical Switch.

## Private workflow

Capture two overlapping windows in separate private executions with the
Stage286 tool. Example video windows:

- First: \`--start-frame 10000 --frames 121\` → indices [10000, 10121).
- Second: \`--start-frame 10060 --frames 121\` → indices [10060, 10181).
- The nominal overlap is **61 video indices**, [10060, 10121).

Supply unique \`--capture-out\` and \`--out\` files for each Stage286 run,
outside the repository. Confirm both capture reports show a zero exit code,
successful container audit, and exactly 121 frames before comparing. Retain
no raw captures in GitHub, Actions, an issue, or a PR.

On the same **private** workstation:

    python tools/wolfmame0106_private_mng_overlap.py ^
      --first C:\private\audits\capture-a.mng --first-start 10000 ^
      --second C:\private\audits\capture-b.mng --second-start 10060 ^
      --out C:\private\audits\overlap-a-b.json

The comparator validates both MNGs using the existing Stage284 bounded
integrity, CRC, embedded PNG and decoded-pixel rules, including matching
dimensions and MNG tick rates. Each frame is hashed privately in process
using SHA-256 of normalized RGBA pixels. Neither hashes nor pixels nor paths
enter the JSON receipt, stdout or public CI. The overlap calculation depends
only on the user-supplied *candidate video* start offsets and counted frames,
not on any assertion about INP record alignment.

Two identical overlap frames are required at minimum. A match involving
changing images is reported as \`CANDIDATE_OVERLAP_PIXELS_EQUAL_UNAUTHENTICATED\`
(exit 0); any mismatch returns the first differing **candidate video index**
(exit 3). If all overlapping frames are static and equal, the result is
\`STATIC_CANDIDATE_OVERLAP_INCONCLUSIVE\` (exit 4). Non-overlapping windows,
different frame formats, invalid files, symlinks or the same underlying file
are blocked (exit 2). A duplicate copy at a different path could still pass;
this tool explicitly never claims it proved independent runs.

The receipt is written exclusively in a private directory with mode 0600;
existing receipts cannot be overwritten. As with other tests, report fields
about emulator identity, original gameplay, actual INP playback and physical
Switch execution stay false.

## Synthetic regression tests (ROM-free)

    python -m unittest discover -s tests -p 'test_wolfmame0106_private_mng_overlap.py' -v

The tests build tiny synthetic MNGs in OS temporary directories and never
contain original ROMs, INP/WLF recordings or game frames. This Draft stage
is stacked on PR #94, does not merge to main, and leaves approved covers and
asset files untouched.

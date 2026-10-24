# Stage384 — private MAME 0.106 original ROM content audit and Wine feasibility

## Stage383 acceptance

All five required CI checks on Stage383 commit `fd2cbe3f` completed
successfully: Python tools, Windows PowerShell synthetic smoke, historical
MAME 0.106 **ROM-free** native preflight, Nintendo Switch bootstrap and
public repository ROM privacy gate. Draft PR #139 remains open; `main`
is unchanged.

## Actual private offline original-content verification

Stage384 performed an **owner-private** original `dino.zip` content
audit against the historically pinned MAME 0.106 `dino-driver.xml`
from the independently frozen source-only technical archive.

The exact owner-held Stage369 capsule, Stage381 source-only helper and
Stage383 golden ROM-free technical ZIP passed their original pinned
outer SHA-256 checks before any member was read. The ROM, MAME EXE and
driver XML independently passed the previously published component pins.

The existing offline verifier
`tools/mame0106_private_verifyroms.py` then compared **all 16 of the
historical dino ROM payloads** against the driver-provided entry names,
uncompressed byte counts, CRC32 and SHA-1. Result: **16/16 match**,
7,995,392 bytes of ROM payload checked. The archive CRC and fixed member
inventory checks also passed.

This is an actual check of the owner's original game bytes in a private
Linux workspace. It is more specific than checking only the outer capsule
hash, but **it is not a process execution of MAME**. No emulator was
invoked with original ROM data and no historical `dino.inp` playback,
real capture or Nintendo Switch hardware test is claimed.

The owner-only structured integrity report is stored at
`03_Aggregate_Reports/Stage384_Private_Dino_ROM_Offline_CRC_SHA1_Audit.json`
in the Project Evidence Archive; it includes original-input digests and
must not be committed, copied into CI or served publicly.

## Isolated Wine32 restoration and execution blocker

Recovered the previously owner-archived Debian Trixie Wine32 offline
bundle (three original TAR parts carried in seven Google Drive ZIP
chunks each for parts 00 and 01, plus part 02). The verified reconstructed
TAR contains 426 Debian packages, and every package matched the original
`SHA256SUMS.txt`. Restored the package files into an isolated private
filesystem tree **without installing or replacing system packages**;
also independently verified the archived QEMU i386 helper.

The Wine 10 version probe works, but this host cannot execute the historical
32-bit Windows MAME program:

- Wine32 under QEMU cannot complete the required child process/loader
  path in the available Linux environment.
- Wine64 cannot substitute for the historical 32-bit target; its
  ROM-free `-help` smoke does not complete successfully.
- A compatible owner-controlled Windows machine or Linux Wine32 host
  with functioning 32-bit execution is still required for the actual
  historical `-verifyroms dino` process.

No original ROM was supplied to these unsuccessful host/runtime smoke
tests, and **the absence of a native receipt remains explicit**.
Private Wine diagnostic logs and safe aggregate host results are archived
separately in `04_Logs_and_CI` and `03_Aggregate_Reports`.

## Durable private evidence and next gate

Stage384 archived four owner-only artifacts on Google Drive:

1. Actual original ROM/driver CRC and SHA-1 result, `03_Aggregate_Reports`
2. Local Wine/QEMU host feasibility report, `03_Aggregate_Reports`
3. Technical Wine probe logs ZIP, `04_Logs_and_CI`
4. Evidence manifest with exact post-upload/download SHA-256,
   `00_Manifest_and_SHA256`

Each was read back and matched byte-for-byte; all four are `shared=false`
and granted only to the owner. Raw original ROM bytes, game assets,
captures and traces remain outside the public repository.

The next actual execution gate is the pinned owner-private
`MAME 0.106 -verifyroms dino` run on a compatible private machine,
followed by independent Stage379 receipt audit. Only once that result is
genuinely observed should original `dino.inp` playback be attempted.
A successful offline check must never be promoted into native execution
evidence.

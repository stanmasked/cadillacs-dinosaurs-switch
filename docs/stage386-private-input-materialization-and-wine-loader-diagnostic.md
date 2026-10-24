# Stage386 — private input revalidation and local Wine loader diagnosis

## Owner-private inputs revalidated

Fetched the existing owner-only `dino.inp` and `dino.wlf` records from
Google Drive into the isolated local workspace. Both exact byte counts and
SHA-256 digests matched the owner-only Stage352 manifest. The files were
copied into the isolated private-original workspace with mode `0600`;
the Drive originals were not changed.

The original ROM ZIP and historical MAME executable were also checked against
their already pinned component digests. This is input-materialization evidence,
not game execution.

The private audit record is stored in the project's owner-only
`03_Aggregate_Reports` folder as
`Stage386_Private_Input_Materialization_Audit.json`. The local Wine loader
diagnostic is stored separately as
`Stage386_Local_QEMU_Wine_Loader_Diagnostic.json`. Both reports were
uploaded and read back; neither contains original game bytes or raw input
recordings.

## Stage385 independent recheck

The Stage385 offline auditor was run again in the isolated local workspace
against the actual owner-private Stage369 capsule, the pinned Stage383
ROM-free technical archive, and the unchanged Stage384 report. It again
verified all 16 expected ROM members by historical driver filename, size,
CRC32 and SHA-1 (7,995,392 payload bytes). The independent report and its
source-only helper were already saved in the private evidence archive.

This remains an offline content audit. The executable was not run against
the original ROM in this check.

## Local Wine/QEMU blocker

A local ROM-free `MAME -help` attempt was made using the recovered Wine32
root filesystem and the pinned QEMU i386 helper. Wine's version probe works,
but the Windows process does not start: the local QEMU user-mode process
cannot execute Wine's nested i386 loader, and the available container does
not permit mounting/registering `binfmt_misc`. The diagnostic captures
the observed failure class and component digests without logging private
paths or game data.

An unmodified PRoot test was insufficient because it classified i386 ELF
files as compatible with the x86-64 host. A source-pinned PRoot variant is
being tested that removes `EM_386` from the x86-64 host-ELF list, so that
32-bit ELF children must be routed through QEMU while native x86-64 helper
processes remain native. The regression must explicitly confirm both the
child's expected exit code and actual QEMU invocation markers before the
helper can be used locally. Until that gate passes, it is not an accepted
runtime solution.

## Acceptance state and next gate

- Owner-only input copies and reports: SHA-256 revalidated.
- Stage385 ROM content check: repeated successfully offline.
- Native MAME `-verifyroms dino`: **not executed**.
- Original `dino.inp` playback: **not executed**.
- Nintendo Switch emulator/hardware run: **not executed**.
- Original ROM, INP/WLF, extracted assets and raw captures: not uploaded to
  public GitHub or GitHub Actions artifacts.
- PR #139 remains Draft; `main` is unchanged.

Next: finish the forced-i386 QEMU bridge's synthetic regression. If it passes,
test only the historical MAME executable's ROM-free help path locally first.
Attempt `-verifyroms dino` only if that succeeds, and attempt original input
playback only after genuine ROM verification succeeds. Never promote an
offline hash audit or a synthetic CI result into native execution evidence.

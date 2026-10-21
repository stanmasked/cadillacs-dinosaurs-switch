# Stage283 — reproducible historical MAME 0.106 runtime build

## Why

Stage282 proves that the private user's ROM archive contains the 16 exact
payloads required by the original `mamedev/historic-mame` `mame0106`
driver for `dino`. The remaining local tool gap is an executable capable
of exercising the historical driver. This workflow attempts a **ROM-free**
build of the official upstream MAME 0.106 source.

Source is pinned to commit
`0a83d596c83b4d1a72cb3a7b1d2835b809206f2f`, resolved from the public
`mame0106` tag:
https://github.com/mamedev/historic-mame/tree/mame0106

## Build and artifact

The existing `.github/workflows/python-tests.yml` workflow has an opt-in
build job: it runs on this specific PR branch and can be run manually after
that workflow is available on the default branch. It builds a 32-bit Windows
executable with MinGW from that source. The artifact contains:

- `mame0106.exe` — compiled upstream MAME 0.106, **not WolfMAME**;
- `mame0106-source.zip` — the corresponding pinned source tree;
- `COPYING` — upstream licence text;
- `source-pin.txt` and `SHA256SUMS.txt` — source and binary provenance;
- `runtime-status.txt` — explicit limits of the artifact.

Artifact retention is three days. No original ROM, INP/WLF, screenshots,
recorded controls or user data enter the workflow or artifact. This build
uses only publicly available source.

## Important limits

This is a toolchain experiment, not an original gameplay result:

- WolfMAME-specific validation/anti-cheat additions are **not included**.
- `dino.inp` playback has **not** been run by this build workflow.
- `dino.wlf` has **not** been validated by the built executable.
- The build does not claim that original gameplay frames were produced.
- It does not claim Nintendo Switch hardware parity.

A successful build would give us a source-pinned historical MAME executable
to try against the private `dino.zip` on a compatible Windows environment.
The actual WolfMAME 0.106 recording remains the authority for the requested
original playback; any later MAME playback must be treated as a separate
compatibility experiment, not a replacement for it.

## Why not include the ROM in CI?

The repository is public. The user's copyrighted ROM archive and private
recording stay outside GitHub. The executable can be built independently
from source; a local authorized copy of `dino.zip` is used only on the
private workstation for any future ROM audit or replay attempt.

## Verification

The workflow checks the exact upstream commit before building and refuses
to continue if the tag resolves to another commit. It uploads the source
alongside the binary and computes SHA-256 checksums for the binary and
source archive. The artifact is intentionally short-lived and ROM-free.

Stage283 is stacked on Draft PR #90. The build job is deliberately scoped
so unrelated PRs do not pay the cost of compiling this 2006 codebase. It does
not modify `main`, original
input files, ROM bytes, or approved cover artwork.

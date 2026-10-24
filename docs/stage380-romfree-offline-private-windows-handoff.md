# Stage380 — durable ROM-free owner-private Windows helper handoff

## Goal

Previous Stage379 `2c03e5ea` passed all five mandatory GitHub Actions.
The private `Stage369_MAME0106_Private_Windows_Verify_Capsule.zip`
is intact and securely stored in owner-only Google Drive, but this Linux
session does not provide a usable Windows/Wine runtime. **The historical
game/ROM has not been executed here.**

Make the source-only Windows verification and report-audit tools portable
to a private Windows machine without requiring its user to clone the
entire public source tree, and persist that portable helper independently
of short-lived GitHub Actions artifacts.

## Stage380 artifact

`tools/mame0106_private_helper_handoff.py` creates a deterministic ZIP
named `stage380-romfree-helper.zip` containing only:

- Eight explicit public Python modules for Stage369 capsule validation,
  the private Windows runner, independent JSON audit and their dependencies
- `STAGE380-PRIVATE-WINDOWS-RUNBOOK.txt`
- `STAGE380-SHA256-MANIFEST.json` with every module's length and SHA-256,
  the producing source Git commit and explicit `private_game_execution`
  evidence boundaries

There is **no directory walking or glob search**; every allowed pathname
is in a fixed constant allowlist, and the resulting ZIP must contain exactly
10 members with safe regular-file modes, valid CRCs, size limits and SHA-256
matching the manifest. The source-only ZIP includes **no**
`roms/dino.zip`, `mame0106.exe`, `dino.inp`, `dino.wlf`, extracted
game textures, or original captures.

New public synthetic tests check determinism, source modification,
missing/additional members, bad SHA, forged claims, symlinks, oversized
source, no overwrite, and bundling exactly the 8 real public source files.
They do not run MAME or open game material.

The existing Windows synthetic-only GitHub workflow now runs these tests
and builds the helper ZIP only if earlier checks pass. Its ROM-free artifact
has short retention (3 days). Immediately **copy and SHA-256 readback
verify** the ZIP in the owner-only Google Drive Project Evidence Archive
folder `07_Builds_and_Test_Artifacts`. The GitHub artifact is an ephemeral
transport, not the authoritative archive.

## Private Windows use, not yet performed

Obtain the intact, owner-only Stage369 original separately from Google Drive,
verify its pinned SHA-256
`fa6ff589b109db70c8231bf7713ec50cf5b9a15b58e43bb3b6705bc25e4bd19d`
and keep it **outside** any public repository or runner.

On an isolated, owner-controlled Windows PC or VM with Python 3.11+,
verify the helper outer ZIP against its Drive SHA-256, extract its 10
source-only members and validate the nine internal manifest records.

Run `python -m tools.mame0106_private_execution_session` with
`--capsule` pointing to the original private Stage369 ZIP and a new
`--session-dir`, then run the independent
`python -m tools.mame0106_private_session_audit` with
`--require-native-positive`. The ZIP runbook contains explicit commands.

Even a positive result is **local self-reported native execution**, not
a cryptographically independent attestation, not `dino.inp` playback
and not proof of a physical Nintendo Switch run. Record the true status.
A failure must not produce a fake successful receipt.

Store actual receipts, session manifests and SHA-256 readbacks privately
under `03_Aggregate_Reports` before any local cleanup. `main` is
unchanged and PR #139 remains Draft.

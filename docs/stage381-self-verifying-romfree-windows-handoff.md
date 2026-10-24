# Stage381 — self-verifying ROM-free Windows handoff (v2)

## Purpose

Stage380 prepared an owner-private Windows helper, but its original ZIP
contained eight Python modules without the ZIP verifier itself. A Windows
host could run the verification code only after separately obtaining
`tools/mame0106_private_helper_handoff.py` from GitHub. This was an
unnecessary external dependency at the most critical handoff point.

Stage381 fixes that by adding the **ninth source-only Python module**,
`tools/mame0106_private_helper_handoff.py`, to the fixed allowlist. The
new versioned archive contains **11 items**: nine Python modules,
a human-readable runbook and a JSON manifest with SHA-256/size pins for
all ten non-manifest entries. No ROM, MAME executable, original input
recordings, extracted game assets or raw captures are included.

The version is deliberately distinct from the archived Stage380 bundle:

- ZIP content schema: `cadillacs-stage381-owner-private-python-helper-romfree-v2`
- Runbook: `STAGE381-PRIVATE-WINDOWS-RUNBOOK.txt`
- Manifest: `STAGE381-SHA256-MANIFEST.json`
- CI artifact: `stage381-romfree-owner-private-python-helper`

The old Stage380 owner-private archive and its SHA manifest remain valid
historical artifacts and are not overwritten.

## Independent Windows ZIP check

On a private owner-controlled Windows PC (with Python 3.11+), independently
verify the ZIP's **outer SHA-256** against the owner-only Drive evidence
manifest before extracting. Then extract just the 11 fixed source-only
members into a new clean folder and run in PowerShell from that folder:

```powershell
python -m tools.mame0106_private_helper_handoff --verify "C:\Private\stage381-romfree-helper.zip"
```

The verifier must return `status=romfree_helper_source_only`,
`members=11` and exit code 0, confirming CRCs, exact inventory, regular
files, exact manifest and content SHA-256. A mismatched or tampered helper
archive stops before any original game data is touched.

An optional `--expected-revision <40-hex Git SHA>` pins the source revision
to an independently recorded value. A self-consistent manifest **cannot**
authenticate the source revision on its own; the outer ZIP hash recorded
separately in owner-only Drive remains the authoritative handoff identity.

Only after both checks may the owner separately obtain the unmodified
private Stage369 capsule, execute
`python -m tools.mame0106_private_execution_session` on a private Windows
host and independently audit the resulting local report using
`python -m tools.mame0106_private_session_audit`.

## Tests and retention

The public Windows synthetic CI tests now unpack the ZIP and spawn its
own contained verifier against the original ZIP. It also rejects an
altered embedded verifier, incorrect source revision, extra or missing
members, changed SHA manifest and source symlinks. No real ROM or MAME
is used in those tests.

Once GitHub Actions succeeds, the **entire exact v2 ZIP** must be copied
from its short-retention CI artifact to the owner-only Google Drive
`07_Builds_and_Test_Artifacts` folder, downloaded back, checked by
SHA-256 and CRC, and registered under `00_Manifest_and_SHA256`. Leave
Stage380 and Stage369 sources unchanged. All game-derived data remains
private; public GitHub contains only source and synthetic tests.

Neither Stage380 nor Stage381 is a genuine `-verifyroms dino` result,
an INP replay or a Nintendo Switch hardware test. PR #139 stays Draft,
`main` remains unchanged until validated native evidence exists.

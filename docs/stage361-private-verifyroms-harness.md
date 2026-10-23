# Stage361 — gated private verification, not a replay claim

Prerequisite: Stage360's owner-only Google Drive copy of the name-adapted
`dino.zip`, matching source-pinned historical MAME 0.106 XML and executable.
No original ROMs, INP/WLF, extracted game graphics, or detailed private traces
may be committed to this repository or sent to public GitHub Actions.

The Stage361 tool has **two intentionally distinct** outcomes:

1. Offline content audit: pinned SHA-256 of private ZIP and historical driver
   XML, 16 exactly named entries, independent uncompressed size/CRC32/SHA-1
   checks against the original MAME 0.106 `dino` driver. It has been run on the
   recovered private assets (16/16). Status: `offline_only` (exit code 2).
2. Genuine Windows native verification: after offline audit, run the exactly
   SHA-256-pinned `mame0106.exe` on a private Windows host with original ROM
   payload staged in a short-lived isolated scratch directory. Require BOTH
   the historical frontend's `romset dino is good` and
   `1 romsets found, 1 were OK.` markers and process exit code 0. Only then
   report `native_verified`. Raw stdout/stderr and ROM copies remain in an
   automatically deleted scratch directory; stdout to the operator has only
   numeric aggregate fields and a fixed result classification.

Example operator commands from the project root, **locally, not in CI**:

```sh
python -m tools.mame0106_private_verifyroms \
  --rom-zip /private/scratch/dino.zip \
  --driver-xml /private/scratch/pinned-mame0106-listxml.xml
```

After recovering the original pinned MAME executable on a private Windows
machine, repeat with the explicit `--mame-exe C:/private/scratch/mame0106.exe`
option. The tool refuses original-data inspection whenever `GITHUB_ACTIONS=true`.
Do **not** upload private inputs, private output or raw logs to GitHub Actions;
if using cloud runners, a physically isolated owner-managed private environment
must exist first. The offline audit above does not require Windows.

Source corroboration: historical MAME 0.106 `src/windows/fronthlp.c` verifies
ROMs using the `-verifyroms` frontend flag; its success branch prints the two
required markers. Its Windows configuration has `rompath` and `readconfig`.
The harness passes `dino -verifyroms -rompath <private-scratch> -noreadconfig`.

Stage361 local results: 12 synthetic tests passed; a separate fresh local
private audit matched all 16 entries, 7,995,392 unpacked bytes, and rejected
claiming MAME execution (`rom_execution=not_run_no_executable_selected`,
`result=offline_only`). This runtime does not have Wine or a native Windows
execution environment. No recorded input replay or gameplay capture occurred.

Private canonical files, per-file mapping details and this stage's raw asset
validation are recorded in the private project Google Drive manifest and handoff.
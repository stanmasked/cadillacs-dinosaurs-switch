# Stage376 — sealed owner-private Windows MAME verification session

## Goal and evidence boundary

The Stage369 private owner-held ZIP, source-pinned by SHA-256
`fa6ff589b109db70c8231bf7713ec50cf5b9a15b58e43bb3b6705bc25e4bd19d`,
contains historical MAME 0.106 and the owner's `dino` ROM. No code
in this public repository may upload that ZIP, extracted files, original
`dino.inp` or `dino.wlf`, raw captures or graphics to GitHub Actions.

Stage374/375 ran the genuine MAME executable on a public Windows runner for
ROM-**free** technical checks only. This is not evidence of native private
`-verifyroms dino`.

Stage376 adds a source-only **owner-private one-pass entry point**:
`tools/mame0106_private_execution_session.py`. On a privately controlled
Windows PC or VM, outside `GITHUB_ACTIONS`, it:

1. Refuses non-Windows or public CI before creating files.
2. Requires a **new** session directory outside Git checkout; checks parent
   symlinks/reparse points. Never overwrites earlier evidence.
3. Uses Stage371 pinned capsule validation and its private native PowerShell
   execution with the existing timeouts and fixed status markers.
4. Classifies the receipt with the Stage372/373 independent schema gate.
5. Refuses to create a success manifest when process and evidence disagree.
6. Writes just `stage376-native-receipt.json` and
   `stage376-session-manifest.json`, with the exact receipt SHA-256 and size,
   native positive/negative grade, private capsule pin and false
   `wolfmame_inp_playback_executed` and physical Switch flags.
7. Re-reads the manifest/receipt before returning. Output to console is fixed
   status metadata; raw emulator stdout/stderr is never embedded in reports.
8. Leaves interrupted partial session data in private storage for forensic
   review; it never declares a partial run successful.

Example commands on an **owner-controlled private Windows machine** with
Python 3 and a source-only checkout (paths are examples, not files that
exist on this host):

```powershell
python -m tools.mame0106_private_execution_session --capsule "C:\Private\Stage369_MAME0106_Private_Windows_Verify_Capsule.zip" --session-dir "C:\Private\Stage376-unique-session"
```

Exit codes: **0** means a positive local self-report; **3** means a negative
local self-report; **2** means refused, incomplete or invalid evidence.
A positive self-report is **not** cryptographically authenticated third-party
attestation. A nonzero exit does not justify deleting private partial
evidence before inspecting and archiving it. This command does not replay
`dino.inp` and does not verify a physical Nintendo Switch.

## Archive after the real run

The receipt and its SHA-256 manifest, the privately held capsule and future
raw/aggregate captures belong exclusively in the owner-only Google Drive
**Cadillacs and Dinosaurs Remake / Project Evidence Archive**. Place derived
JSON and session manifests under `03_Aggregate_Reports` and the original ZIP
under `01_Private_Originals` (or the existing private Stage369 folder).
Check owner-only permission, independently download/read back each file and
verify the SHA-256 before any temporary local cleanup. Do not commit outputs.

## What Stage376 tests establish

Public Windows CI uses only synthetic JSON and mocked process responses.
The tests cover negative status, forged disagreement, missing input, private
storage refusal, destructive overwrite prevention, symlink redirection and
absence of raw game data. These tests **do not run the original ROM**.

At the time of implementation, no owner-controlled Windows host capable of
opening the private Stage369 archive is available to this execution session.
Real private `MAME 0.106 -verifyroms dino` remains pending. Keep PR #139
Draft and keep `main` unchanged until real evidence exists.

# Stage371 — owner-private MAME 0.106 Windows execution receipt

The Stage369 private ZIP is intact in owner-only Google Drive; its actual
`mame0106.exe`, `roms/dino.zip`, `verifyroms.ps1`, and embedded `capsule.json`
were already source-pinned and verified offline. **None of these assets belong
in public GitHub or GitHub Actions**.

Stage371 adds a **source-only** wrapper for an owner-controlled, offline Windows
PC/VM, rather than uploading any private binaries to a public Windows runner.
It independently verifies the exact pinned *outer* Stage369 ZIP SHA-256 and
all four capsule entries through the Stage369 inspector before unpacking to a
new temporary directory. It invokes the unchanged, pinned PowerShell verifier
with a bounded 135-second outer timeout and captures at most bounded status
output (never prints or saves real MAME stdout, stderr or game content).

## Private host commands

The archive and receipt path must be outside the public Git working tree, on
owner-controlled non-synced private storage. Run in Windows PowerShell or a
terminal with Python 3 installed, from a source-only checkout of this project:

```powershell
python -m tools.mame0106_private_native_receipt --capsule "C:\Private\Stage369_MAME0106_Private_Windows_Verify_Capsule.zip" --verify-only
python -m tools.mame0106_private_native_receipt --capsule "C:\Private\Stage369_MAME0106_Private_Windows_Verify_Capsule.zip" --receipt "C:\Private\Stage371-unique-evidence.json"
```

`--verify-only` is safe for *offline integrity checks* and returns
`native_mame_verification_executed=False`. It does not produce a runtime receipt.
The execution command refuses GitHub Actions, non-Windows hosts, unsafe or
already-used receipt paths, source files inside public repositories, wrong
capsule SHA-256 and any ZIP member mismatch. No existing report is overwritten.

If the real private PowerShell process exits 0 and emits exactly the three
expected status lines with empty stderr, the new local JSON receipt can report
`native_rom_verification_status=native_verified`. All other complete outcomes
are marked `not_verified`. A timeout, missing executable or unsafe host fails
closed without an execution claim. Receipts contain only fixed metadata,
source checksums and boolean observations. **Do not commit receipts**: they
belong in owner-only Google Drive after independent readback verification.

A local receipt is **not a cryptographically authenticated attestation** and
cannot, by itself, prove a third party actually executed MAME. It is an audit
record of the owner-controlled Windows process and should be evaluated with the
host/session provenance. It never claims an original `dino.inp` playback or
physical Switch test.

## Evidence available now

- Stage369 source-only Python, Switch and Windows synthetic CI succeeded.
- Stage370 original MAME source-contract audit: 18/18 checks, no real game run.
- Stage371 offline verifier independently checks the owner-only Stage369 ZIP.
- Stage371 tests are **synthetic only**; patching the host guard in unit tests
  never causes real ROM or a genuine Windows PE executable to be started.
- Real historical `MAME 0.106 -verifyroms dino` on an owner-controlled Windows
  machine is **still not executed** until a native receipt is produced.

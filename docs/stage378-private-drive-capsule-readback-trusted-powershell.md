# Stage378 — private Stage369 capsule readback and trusted Windows PowerShell

## Independently verified private Drive original

The owner-only Google Drive file
`Stage369_MAME0106_Private_Windows_Verify_Capsule.zip`
(ID `1jAtoLOqIt7IF8UQ0CiBfYcQItfBxScZC`) was independently
downloaded and checked in a private Linux workspace on 2026-10-24.
This was an **offline archive check**, not an emulator execution.

- Size: 29,169,673 bytes; matches the pinned Stage369 byte count.
- Outer SHA-256: `fa6ff589b109db70c8231bf7713ec50cf5b9a15b58e43bb3b6705bc25e4bd19d`.
- ZIP CRC check: passes.
- ZIP inventory: exactly `mame0106.exe`, `roms/dino.zip`,
  `verifyroms.ps1` and `capsule.json`.
- Internal manifest: `mame0106-private-windows-capsule-v1`;
  `execution_status=not_executed`.
- Three component SHA-256 and byte-count comparisons against that
  internal manifest: 3/3 matched.
- Google Drive permissions: file is not shared, owner only.

The manifest digests were checked against the actual ZIP members; that is
independent of the previous Stage371 private preflight but is **not**
independent cryptographic authentication of the manifest's origin.
The source is retained untouched in its owner-only Google Drive folder.
No game bytes are committed to the public GitHub repo.

## Host limitation

The current execution environment is Linux x86_64 without `wine`,
`wine32`, `qemu-i386-static`, `pwsh` or Windows PowerShell. The
private Windows MAME `-verifyroms dino` command **did not run** here.
The actual historical `dino.inp` playback also remains unverified.

## Runtime resolution hardening

The owner-private native runner formerly called `powershell.exe` by
executable name, allowing Windows `PATH` lookup. Stage378 replaces this
with an absolute WindowsPowerShell path rooted in the OS directory returned
by Win32 `GetSystemWindowsDirectoryW`, not `PATH` or a mutable
`SystemRoot` environment variable. The runner verifies that the resolved
WindowsPowerShell executable exists and is not a symlink/reparse point;
otherwise it fails before launching a process.

Public Windows CI tests remain ROM-free. The synthetic suite now verifies:

1. A poisoned `PATH` cannot change the executable selected for the
   private subprocess.
2. Failure to resolve trusted system PowerShell prevents the subprocess.
3. On Windows, the OS-resolved PowerShell file exists (no game invocation).
4. All existing Stage371/377 snapshot hashing and native receipt
   classification regressions continue to pass.

A resolved OS executable is still not a third-party attestation of private
execution and cannot guarantee that an administrator has not tampered with
the host. Run the real private verifier only on an isolated owner-controlled
Windows PC/VM, with its private original ZIP outside any public CI checkout.

The Stage376 session command remains:

```powershell
python -m tools.mame0106_private_execution_session --capsule "C:\\Private\\Stage369_MAME0106_Private_Windows_Verify_Capsule.zip" --session-dir "C:\\Private\\Stage378-first-native-session"
```

Never assume these example paths exist. A fresh, owner-only session directory
is required. A `native_positive_local_self_report` remains a local
self-report until corroborated; the XML/protocol and INP/WLF replay gates
remain separate. All private receipts and derivative manifests must be
uploaded to owner-only Google Drive and read back with SHA-256 before
temporary cleanup. PR #139 remains Draft and `main` unchanged.

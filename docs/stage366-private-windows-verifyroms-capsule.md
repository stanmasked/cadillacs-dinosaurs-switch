# Stage366 — private, portable Windows ROM verification capsule

The source-pinned historical Windows MAME 0.106 executable was already built
and passed ROM-free launcher checks. The owner-held game archive was separately
relabelled without altering payload bytes and audited against the pinned
MAME 0.106 `dino` driver XML. A **genuine native `-verifyroms dino` invocation**
has **not** been observed in this development environment, which lacks Wine
and Windows native execution. The next step needs an offline, owner-controlled
Windows PC or VM. GitHub-hosted runners are never an acceptable place to put
private ROM bytes, even temporarily.

## Private capsule packaging

The public, source-only tool `tools/mame0106_private_windows_capsule.py`
accepts three files whose SHA-256 hashes are pinned by the existing project
code: the ROM-free verified `mame0106.exe`, owner-private relabelled `dino.zip`,
and the historical `dino-driver.xml`. It runs exact offline ROM-by-ROM checks
*before* packaging, verifies that the exe is a pinned PE32/i386 binary, and
writes one new ZIP with four fixed entries:

- `mame0106.exe` — verified historical Windows binary
- `roms/dino.zip` — **PRIVATE original game content**
- `verifyroms.ps1` — minimal owner-offline Windows PowerShell 5.1 runner
- `capsule.json` — PRIVATE file hashes, sizes and non-execution status

The resulting ZIP **contains game assets** and must remain in an owner-only
private repository/folder such as the project's Google Drive archive. Do not
commit, issue-attach, artifact-upload, email publicly, or paste its contents.
The builder refuses GitHub Actions, existing outputs, symbolic links, source
files under the public source tree, and interrupted `.pending` copies. New
copies are non-destructive. The ZIP itself is independently reopened and its
entry hashes and ZIP CRCs are checked after it is built.

Use it from the project root only on an owner-controlled host, with actual
private source paths outside the public tree:

```sh
python -m tools.mame0106_private_windows_capsule \
  --exe <PRIVATE_SOURCE_PINNED_MAME0106_EXE> \
  --rom <PRIVATE_ADAPTED_DINO_ZIP> \
  --driver-xml <PRIVATE_PINNED_DRIVER_XML> \
  --out <NEW_PRIVATE_WINDOWS_CAPSULE_ZIP>
```

The private archive is backed up to owner-only Drive. To use it on a private
Windows machine, independently compare the archive SHA-256 against its
owner-only Drive manifest, extract into a new local, non-synced directory,
and invoke `powershell.exe -NoProfile -File .\verifyroms.ps1` there. On a
machine with restrictive script policy, adjust only that local process under
the owner's own security policy. No Python is needed for this Windows phase.
The runner checks hashes again, copies the exe and ROM into temporary private
storage, enforces a 90-second deadline, checks process exit code and both
historical MAME success lines, prints only a coarse result and deletes temp
logs. Do not copy or submit unredacted emulator output to public CI.

A `status=native_verified` printed on a real Windows host would support a
bounded historical `dino` ROM verification. Such a status has **not** yet been
obtained; the script itself has only been checked statically and through
synthetic Python unit tests, not on Windows. It does **not** replay the
WolfMAME input file or prove visual frame fidelity.

## Validation performed for Stage366

- Input exe, private ROM and historical driver XML hashes matched their
  previously owner-pinned values.
- Private capsule was built offline, four ZIP members, SHA/CRC verified.
- Twelve synthetic-only unit tests passed under `GITHUB_ACTIONS=true`;
  test fixtures never contain game ROM bytes.
- Capsule, detailed private manifest and sanitized status receipt were stored
  in owner-only Google Drive, then downloaded again and checked byte-for-byte.
- No actual Windows MAME process was started; no `dino.inp` was replayed;
  no screenshots or copyrighted graphics were placed in public CI.

Privacy rule for all projects: original game binaries, derived graphical
assets, input recordings, raw traces and detailed private reports belong only
in the owner-only Google Drive project archive, never in public GitHub.
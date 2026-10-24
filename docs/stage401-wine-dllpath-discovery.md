# Stage401–403 — private Wine DLL search-path diagnosis

## Stage401 finding

The extracted Debian Wine 10.0 runtime contains the i386 Wine Unix libraries, including `i386-unix/ntdll.so`, but its local launch path did not inherit `WINEDLLPATH`. In the private PRoot/QEMU test, `wine --version` failed with `wine: could not load ntdll.so: (null)` when the variable was unset. Setting `WINEDLLPATH` to the i386 Unix-library directory made the same version probe exit successfully and print `wine-10.0 (Debian 10.0~repack-6)`.

The extracted runtime is not a full package installation: maintainer scripts and alternatives links were not run. That makes relying on default Wine path discovery less reproducible than using an explicit path.

## Stage401 change

- The guarded private MAME launcher derives `WINEDLLPATH` from existing Debian multiarch Wine directories only when the caller has not supplied an override.
- Regression tests cover path discovery and caller-override preservation.

## Stage402 correction

The first Stage401 workflow edit explicitly exported only the parent Wine directories. Stage402 added the Unix-specific library directories. The subsequent architecture audit found that both blocks initially used the same order, which is inappropriate for the 64-bit fallback.

## Stage403 correction

The Wine32 bootstrap now prioritizes `/usr/lib/i386-linux-gnu/wine/i386-unix` and its i386 parent before the amd64 paths. The native Wine64 fallback prioritizes `/usr/lib/x86_64-linux-gnu/wine/x86_64-unix` and its amd64 parent before the i386 paths. Regression tests assert the exact distinct path lists and check the order within each workflow block. Caller-supplied `WINEDLLPATH` remains untouched by the launcher.

## Limits

A local MAME `-help` attempt under the extracted-rootfs PRoot/QEMU bridge still did not complete and eventually reported a `kernel32.dll` load failure; the process also produced child-process and file-descriptor errors. These changes address DLL search-path configuration only. They do **not** establish that MAME starts in this PRoot environment, that the native Wine64 fallback works, or that the original game and recording can be replayed.

All diagnostics used the ROM-free technical MAME artifact and public Wine packages only. No original ROM, `dino.inp`, `dino.wlf`, extracted game resources, or gameplay captures were used. Keep PR #139 Draft and `main` unchanged until a real private replay passes the independent frame/trace checks.

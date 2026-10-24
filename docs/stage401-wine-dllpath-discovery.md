# Stage401–402 — private Wine DLL search-path diagnosis

## Stage401 finding

The extracted Debian Wine 10.0 runtime contains the i386 Wine Unix libraries, including `i386-unix/ntdll.so`, but its local launch path did not inherit `WINEDLLPATH`. In the private PRoot/QEMU test, `wine --version` failed with `wine: could not load ntdll.so: (null)` when the variable was unset. Setting `WINEDLLPATH` to the i386 Unix-library directory made the same version probe exit successfully and print `wine-10.0 (Debian 10.0~repack-6)`.

The extracted runtime is not a full package installation: maintainer scripts and alternatives links were not run. That makes relying on default Wine path discovery less reproducible than using an explicit path.

## Stage401 change

- The guarded private MAME launcher derives `WINEDLLPATH` from existing Debian multiarch Wine directories only when the caller has not supplied an override.
- Regression tests cover path discovery and caller-override preservation.

## Stage402 correction

The first Stage401 workflow edit explicitly exported only the parent Wine directories. That explicit value prevented the launcher's fallback discovery from running, and it did not match the locally successful `i386-unix` path. Stage402 corrects both workflow exports (Wine32 bootstrap and native Wine64 fallback) to prefer `/usr/lib/i386-linux-gnu/wine/i386-unix` and `/usr/lib/x86_64-linux-gnu/wine/x86_64-unix`, followed by the parent directories. Regression tests now require both exact exports and verify that Unix-specific paths precede the parent fallbacks.

## Limits

A local MAME `-help` attempt under the extracted-rootfs PRoot/QEMU bridge still did not complete and eventually reported a `kernel32.dll` load failure; the process also produced child-process and file-descriptor errors. This change addresses DLL search-path discovery only. It does **not** establish that MAME starts in this PRoot environment, that the native Wine64 fallback works, or that the original game and recording can be replayed.

All diagnostics used the ROM-free technical MAME artifact and public Wine packages only. No original ROM, `dino.inp`, `dino.wlf`, extracted game resources, or gameplay captures were used. Keep PR #139 Draft and `main` unchanged until a real private replay passes the independent frame/trace checks.

# Stage401 — make private Wine DLL discovery deterministic

## Finding

The extracted Debian Wine 10.0 runtime contains the i386 Wine Unix libraries, including \`i386-unix/ntdll.so\`, but its local launch path did not inherit \`WINEDLLPATH\`. In the private PRoot/QEMU test, \`wine --version\` failed with \`wine: could not load ntdll.so: (null)\` when the variable was unset. Setting \`WINEDLLPATH\` to the Debian multiarch Wine directories made the same version probe exit successfully and print \`wine-10.0 (Debian 10.0~repack-6)\`.

The extracted runtime is not a full package installation: maintainer scripts and alternatives links were not run. That makes relying on the system's default Wine path discovery less reproducible than using an explicit path.

## Change

- The guarded private MAME launcher now derives \`WINEDLLPATH\` from existing Debian multiarch Wine directories only when the caller has not supplied an override.
- The Wine32 workflow exports the same explicit path before Wine prefix initialization and the MAME help/config/listxml probes.
- Regression tests check the default-path candidates, caller override preservation, and workflow ordering.

## Limits

A subsequent local MAME \`-help\` attempt under the extracted-rootfs PRoot/QEMU bridge still did not complete and eventually reported \`kernel32.dll\` load failure; the process also produced child-process and file-descriptor errors. This change addresses DLL search-path discovery only. It does **not** establish that MAME starts in this PRoot environment, that the native Wine64 fallback works, or that the original game and recording can be replayed.

All diagnostics used the ROM-free technical MAME artifact and public Wine packages only. No original ROM, \`dino.inp\`, \`dino.wlf\`, extracted game resources, or gameplay captures were used. Keep PR #139 Draft and \`main\` unchanged until a real private replay passes the independent frame/trace checks.

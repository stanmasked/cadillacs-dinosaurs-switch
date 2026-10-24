# Stage397 — correct the Wine64 fallback bootstrap path

## Finding

The Stage356 fallback selected a native Wine64 loader for MAME commands, but initialized its prefix by calling the generic \`wineboot -u\` wrapper. On Debian Trixie, \`/usr/bin/wine-stable\` prefers \`/usr/lib/wine/wine\` (the i386 ELF loader) whenever it exists, regardless of \`WINEARCH=win64\`. Consequently, the supposed Wine64 fallback could silently enter the same 32-bit/QEMU path that had already failed.

## Change

The Stage356 diagnostic now locates the native \`x86_64-windows/wineboot.exe\` PE bootstrap and invokes it explicitly through the detected \`wine64\` ELF loader. It supplies \`WINELOADER\` and the multiarch Wine DLL search roots, records whether the bootstrap PE was found, and fails closed if it is absent. The ROM-free diagnostic explicitly records \`wineboot_invocation=direct_native_wine64_loader\`.

A regression test checks the workflow source so the generic \`wineboot -u\` wrapper cannot be reintroduced into the native Wine64 fallback unnoticed.

## Private local experiment

Using the recovered, checksum-verified Wine package tree and the pinned ROM-free MAME 0.106 artifact:

- Direct native Wine64 prefix initialization returned exit code 0, with Wine service/RPC and driver warnings in the log.
- A subsequent MAME 0.106 \`-help\` attempt in Wine's experimental WoW64 mode did **not** start MAME successfully; Wine emitted an application-start failure. This is not a successful runtime or game-execution result.
- The separate Wine32/QEMU path continues to show nested-process/loader instability.

The change corrects the fallback's test path; it does not claim that Wine64 can run this historical 32-bit MAME build. CI must produce a fresh diagnostic before the next decision.

## Evidence and privacy boundary

All local testing used the ROM-free MAME artifact and public Debian Wine packages only. No original ROM, \`dino.inp\`, \`dino.wlf\`, extracted game resources, or gameplay captures were used. The original-game execution receipt remains absent, and original-data verification remains a separate offline audit.

The change stays on Draft PR #139. \`main\` is not modified.

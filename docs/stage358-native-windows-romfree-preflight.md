# Stage358 — independent ROM-free native Windows verification

Both Wine32 and native Wine64 reached prefix initialization timeouts before
executing MAME. This is not evidence that the original game or recording is incompatible.

The new Windows workflow downloads the pinned ROM-free technical MAME build
from run 39859311511. It validates all eight SHA-256 technical artifact entries,
the independently pinned PE32-i386 executable digest and pinned upstream source.
It then runs bounded MAME -help, -showconfig and -listxml, requiring the original
dino driver and capture-related switches. Full command outputs stay temporary;
only a short aggregate diagnostic is uploaded for three days.

Workflow: .github/workflows/mame0106-windows-romfree-preflight.yml
Runner: tools/mame0106_romfree_native_windows_probe.py
Synthetic tests: tests/test_mame0106_romfree_native_windows_probe.py

No original ROM, INP/WLF, extracted resources, screenshots, raw XML or traces
are supplied. Successful native MAME probing is not proof of private ROM
verification, recording replay, guest execution or physical Switch gameplay.
All original assets and derived game material must remain in private Google Drive.

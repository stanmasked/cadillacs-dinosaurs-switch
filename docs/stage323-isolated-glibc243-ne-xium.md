# Stage323 — compatible glibc 2.43 for pinned public NeXium

Stage322 successfully installed Mesa Lavapipe on the private Debian 13
container, using 25 verified public Debian packages from a one-day
GitHub Actions artifact. A real Xvfb `vulkaninfo --summary` reports
Vulkan 1.4.305 and an LLVM 19 llvmpipe CPU device. The Stage316
opt-in code-only NRO and the upstream NeXium release tarball were
independently pinned to exact SHA-256 values; the exact public emulator
binary was safely extracted into `/opt/cadillacs-stage322-ne-xium`.

The pinned NeXium binary cannot run directly under Debian 13's system
glibc 2.41. Read-only ELF verification shows that it needs
`GLIBC_2.43` from `libm.so.6`. It is NOT SAFE to force-upgrade the
Debian 13 system's libc to satisfy one experimental emulator.

## Safe isolated runtime plan

Fetch the genuine Ubuntu 26.04 package containing glibc >= 2.43 through
a code-only GitHub Actions job. That runner must validate the package
version and verify the ELF symbols `GLIBC_2.43` on libm, then publish
only the public Ubuntu `libc6_*.deb` and its SHA-256 manifest.

On the private Debian 13 machine, verify that archive's manifest,
extract with `dpkg-deb -x` **to a separate /opt runtime directory**,
and invoke the relocated `ld-linux-x86-64.so.2` directly with an
explicit `--library-path` that includes the isolated glibc directory
ahead of Debian's current libraries. Avoid installing the package with
`dpkg -i`, `apt upgrade`, symlink replacement, or changes to the
global `/lib64/ld-linux-x86-64.so.2`.

This isolates the compatibility requirement to the NeXium process and
preserves the operating system's glibc and Vulkan driver installation.

## Evidence boundaries

Installation of the emulator and a compatible loader does NOT establish
original game execution. The subsequent user-private Stage318/321 test
must still authenticate their private 16-member canonical MAME 0.106
`dino.zip`, require exact 4MiB original graphics and canonical
14-frame synthetic state, and observe **actual** NRO guest
`FRAME_SUBMITTED` events and 14 process-bound X11 optical frames.

Private original game ROMs, derived GFX, emulator screen captures,
guest CSV, input movies, Nintendo firmware or keys never enter public
GitHub CI. The `libc6` artifact is a public operating-system package
only and remains separate from any game asset.

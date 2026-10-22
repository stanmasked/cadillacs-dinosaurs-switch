# Stage323 — compatible glibc 2.43 for pinned public NeXium

Stage322 installed Mesa Lavapipe in the private Debian 13 container using
25 verified public Debian packages from a one-day GitHub Actions artifact.
A real Xvfb `vulkaninfo --summary` reports Vulkan API 1.4.305 and an LLVM 19
llvmpipe CPU device. The Stage316 opt-in code-only NRO and the upstream
NeXium release tarball were independently pinned to exact SHA-256 values;
the exact public emulator binary was extracted locally.

The pinned NeXium binary cannot run directly under Debian 13's system
glibc 2.41. Read-only ELF verification showed that it needs `GLIBC_2.43`
from `libm.so.6`. It is unsafe to force-upgrade Debian's system libc to
satisfy one experimental emulator.

## Isolated runtime — verified

The code-only Stage323 GitHub Actions job successfully retrieved the genuine
Ubuntu 26.04 public `libc6` package, checked its architecture and version,
verified the relocated loader and `GLIBC_2.43` in `libm.so.6`, and published
only that public operating-system package with a SHA-256 manifest.

The private installer verified the artifact manifest and package digest,
extracted the package to a separate `/opt` sysroot, and ran the relocated
`ld-linux-x86-64.so.2` with an explicit `--library-path`. Its real
`--list` output confirmed that both `libc.so.6` and `libm.so.6` resolve from
the isolated sysroot. The host's `ldd --version` remained Debian glibc 2.41.
The package was not installed with `dpkg -i`; no global loader, symlink, or
system libc was replaced.

## Private optical verification — passed

A fresh local run of the Stage316 private harness completed successfully
using the pinned NeXium executable, isolated glibc 2.43, Mesa Lavapipe and
Xvfb. Before launch it authenticated the private canonical MAME 0.106
`dino.zip` (all 16 required members), and verified that the private 4 MiB
graphics region and synthetic 14-scene sequence matched the prepared SD
input.

The private receipt reports:

- 14/14 native guest `FRAME_SUBMITTED` events matched the independent Python
  references derived from original graphics.
- 14/14 process-bound host X11 optical frames passed the pixel-match threshold;
  the lowest frame score was 24 matched pixels.
- 11 distinct guest framebuffer samples were observed.
- The receipt was written locally with mode `0600`.

This proves that the isolated loader, Vulkan-capable NeXium process, NRO guest
and process-bound X11 capture can work together on the synthetic scene
sequence. **It does not prove actual original-game execution.** No original
game state, real game VRAM/palette state, `dino.inp`/`dino.wlf` replay, or
physical Nintendo Switch display was verified by this run.

## Evidence and privacy boundaries

Private original game ROMs, derived GFX, raw screenshots, guest CSV, private
paths, source hashes, input movies, Nintendo firmware and keys remain outside
public GitHub and its artifacts. The public Stage323 artifact contains only
the public Ubuntu `libc6` package and its package manifest. The local optical
receipt is redacted and remains private.

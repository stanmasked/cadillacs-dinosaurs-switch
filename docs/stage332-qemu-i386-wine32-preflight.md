# Stage332 — QEMU-assisted Wine32 preflight

## Purpose

The isolated runtime session can execute x86_64 Linux binaries but cannot execute i386 ELF binaries directly. The pinned MAME 0.106 executable is PE32/x86, so Wine64 alone is not a valid substitute for the 32-bit Wine loader.

Stage332 adds a small, separate **QEMU i386 user-mode helper artifact** to the Wine32 packaging workflow. It is a runtime-compatibility experiment only; it does not modify the game, ROM, input recording, or Switch build.

## Reproducible helper packaging

The workflow fetches Debian Bookworm's `qemu-user-static` package at exact version `1:7.2+dfsg-7+deb12u18+b3` through signed APT metadata. It does not install the package. It extracts only `qemu-i386-static` plus its copyright notice and writes version, provenance metadata, and SHA-256 checksums.

The helper artifact has a separate name and retention window from the Wine package. No ROM, INP/WLF, gameplay frame, or user recording is included.

The workflow runs two smoke checks before uploading:
1. `qemu-i386-static --version`.
2. `qemu-i386-static -L / /usr/lib/wine/wine --version`, which exercises the actual i386 Wine ELF through QEMU rather than testing QEMU's CLI alone.

Workflow revision: `798ce47250615c070e00d16265b98349ecaa6312`. The latest observed run is [#39900753138](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39900753138); it was queued at the last check, so the smoke result is **not yet known**.

## Local findings

- The isolated Wine package tree was extracted without maintainer scripts or system-wide package installation.
- Native Wine64 reports version 10.0 from that tree.
- Native Wine64 did not successfully run the PE32 MAME executable; therefore no gameplay conclusion can be drawn from that failure.
- The container cannot directly execute the i386 Wine ELF. QEMU is being tested as a workaround.

## Acceptance gates after the helper becomes available

1. Verify the helper artifact manifest and executable architecture.
2. Confirm the i386 Wine version command exits successfully under QEMU.
3. Confirm the pinned MAME 0.106 `-help` output and `dino` driver listing.
4. Run `-verifyroms dino` against the private ROM directory.
5. Only if those gates pass, stage private `dino.inp` / `dino.wlf` files outside the repository and attempt the bounded first 121 frames.
6. Require a valid MNG with exactly the requested frames, correct dimensions, contiguous trace callbacks, monotonic frame counters, and matching checksums before claiming any original gameplay frames were observed.

A process starting or exiting successfully is not replay proof. Keep PR #139 Draft and do not change `main` until actual source-game playback and visual/trace consistency are demonstrated.

# Stage331 — offline Wine32 runtime portability and private replay readiness

This is a **ROM-free** technical runbook. Never commit or upload original ROMs, INP/WLF recordings, game frames, private captures, or their contents.

## Verified GitHub Actions outcome

- The Stage330 Wine32 bundle workflow completed successfully at run [39867056718](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39867056718).
- Offline installation on a different Debian Trixie patch level exposed a Multi-Arch version mismatch: some i386 libraries were newer than their already-installed amd64 counterparts.
- Commit `8c17e8dd9af70b79fe65007a7b049c54126959dd` augments the Wine32 artifact with **exact amd64 versions** for every cached `Multi-Arch: same` i386 library lacking its amd64 partner. It does **not** place any game-derived bytes into CI.
- The revised workflow completed successfully in [run 39898529084](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39898529084). Artifact `wine32-debian-trixie-offline-packages` (ID `12477068862`) contains 424 Debian packages (the original 400 plus 24 matching amd64 mirrors). The downloaded ZIP SHA-256 and all 424 internal SHA-256 entries were verified in an isolated session.

## Independent local validation

The source-pinned MAME 0.106 technical build from Stage329 (run `39859311511`) was downloaded to the isolated private session. All eight build-manifest SHA-256 checks passed, and the `mame0106.exe` header is PE32 for x86. Metadata binds the source to `mamedev/historic-mame` tag `mame0106` at commit `0a83d596c83b4d1a72cb3a7b1d2835b809206f2f`.

Private inputs remained outside GitHub. The INP's record layout contains 314,951 records of 124 bytes (following its 32-byte header), and an independent digest-based audit matched all 16 entries expected by the ROM-free MAME 0.106 `dino` driver manifest against the private original ZIP.

These are **structural / integrity checks, not replay proof**.

## Current execution limitation

This particular private Linux container runs on x86_64, but executing the i386 Wine ELF loader returns `Exec format error` (the session has no working 32-bit Linux execution compatibility). Installing all 424 packages directly also encounters an unrelated host `systemd` dependency mismatch, so no system-wide installation was performed.

All packages were successfully hash-verified and extracted into an isolated root tree without running maintainer scripts. The 64-bit Wine launcher reports Wine 10.0 when supplied an explicit DLL search path; attempts to run the PE32 MAME executable have **not** reached a successful MAME `-help` exit and have generated **no** original-game MNG capture or counter trace. Do not treat a Wine initialization failure as evidence that the ROM or recording is incompatible.

For the next actual replay, use a **private, trusted x86_64 Linux/Windows host capable of running this i386 Wine32 build**. Check `wine --version` and the pinned MAME 0.106 `-help` and `-listxml` gates before staging any private input. Verify the ROM locally, then attempt the strictly bounded first 121 frames with the previously audited fail-closed capture runner. Require exact MNG frame count and dimensions, valid PNG/container checksums, contiguous CSV callbacks, and monotonic advancement of both trace counters before widening to subsequent windows.

Keep PR #139 Draft and leave `main` untouched until actual source-game playback can be established.
# Stage311 — mount SD before loading diagnostic CPS-1 files

## Observed startup issue

The real Nintendo Switch NRO's `source/main.c` called `load_region()`
for `sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin` **before any
explicit `fsdevMountSdmc()`**. Its only explicit mount happened later,
inside the optional `DINO_EMULATOR_SELFTEST` / `arena_active` branch.

On a guest launch where `sdmc:` was not already mounted by the homebrew
environment, this could silently select the ROM-free geometry arena even
when Stage310's correct artificial files existed in the emulated SD root.
That prevents any useful evidence about sequence frame rendering.

## Fix

- Attempt `fsdevMountSdmc()` once, immediately before `load_region()`,
  in the **normal release and optional emulator modes**.
- Leave the established fallback behavior unchanged. When graphics or SD
  are inaccessible, the invented arena remains available; no real ROM is
  required. If `sdmc:` is already mounted, a redundant mount result does
  not gate opening it.
- Remove the previous late arena-only mount to avoid registering the
  same `sdmc` device twice.
- Preserve `gfx.bin`, `sequence.bin`, `scene.bin` paths and existing
  bounded native loaders, frame CRC verification, 14-scene playback,
  controls and sound policy.

## Reproduce

~~~sh
python -m unittest discover -s tests \
  -p 'test_cps1_switch_sd_mount_311.py' -v
~~~

Six ROM-free startup source regressions check mount order, release/emulator
reachability, single mount, actual SD paths, scene loading after graphics,
and the original no-graphics arena fallback. The normal Nintendo Switch
bootstrap GitHub Action then **compiles the actual modified NRO**.

## Limits and next actual emulator test

This change is a **prerequisite** for a useful NeXium run with the Stage310
synthetic SD bundle. A successful host unit test or NRO compilation is NOT
proof that NeXium mounted that folder, opened either binary, displayed a
scene, or stepped through fourteen frames. That requires a separate
bounded guest-run witness with real emulator execution and, preferably,
host-visible pixel evidence.

No original MAME game, ROM, or INP/WLF replay is involved. Stage311 remains
Draft and stacked on Stage310. Do not merge based only on synthetic CI.

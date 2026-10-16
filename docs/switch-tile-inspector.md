# Nintendo Switch native CPS-1 graphics tile inspector (technical milestone)

This is an **interactive ARM64 homebrew application** built with libnx.
It is not yet a playable game or a true HD asset pack. Its immediate
purpose is to prove original CPS-1 graphics can be consumed by native
Switch code, independently of desktop MAME/Python.

## What the NRO draws

- Native 1280×720 software framebuffer through libnx.
- 16×8 grid of 16×16 decoded CPS-1 tiles per page (128 tiles/page).
- Pages 1–256 cover all 32,768 addressable 16×16 tile code slots.
- Each source pixel is rendered as a sharp 4×4 block, **not HD-restored**.
- The ROM encodes 4-bit palette **indices**, not the actual runtime RGB
  palette. This diagnostic application displays grayscale and optional
  checkerboard for pen 15 (transparency); it does NOT show original colors.

## How to run (your own local files only)

1. From the project root on a computer with Python 3, run:

   ```sh
   python3 tools/cps1_gfx.py /path/to/your/dino.zip --out-local gfx.bin
   ```

2. Confirm `gfx.bin` is **4,194,304 bytes**. The diagnostic program
   checks the length, but does not authenticate all contents.
   The World 930201 reference dump supplied for this private project
   assembles to SHA-256
   `68786de27105ccc64f28f66ad1025f2e6f521aa60ab35c489fb0baaaa8679de1`.
3. On a development-enabled Nintendo Switch SD card, copy:

   ```text
   sdmc:/switch/cadillacs-dinosaurs-switch/cadillacs-dinosaurs-switch.nro
   sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin
   ```

4. Launch `cadillacs-dinosaurs-switch.nro` from Homebrew Menu.
   If the graphics asset is missing, a console screen explains the
   required file and offers PLUS to exit safely.

This app uses the libnx Framebuffer API and reads a file from the
standard Switch `sdmc:/` filesystem. Do **not** upload `gfx.bin`,
original `dino.zip`, extracted sprites, or ROM binaries to GitHub.

### Controls

| Controls | Operation |
|---|---|
| LEFT / RIGHT | Previous / next page |
| UP / DOWN | Jump 16 pages |
| L / R | Jump 8 pages |
| A | Invert synthetic grayscale |
| B | Toggle checkerboard for transparent pen 15 |
| Y | Toggle tile-grid borders |
| PLUS | Exit to Homebrew Menu |

## Build and correctness checks

```sh
# ROM-free host correctness test of the exact C decoder used by the Switch build
gcc -std=c11 -O2 -Wall -Wextra -Werror -Isource \
  tests/cps1_tile_native_test.c source/cps1_tile.c -o /tmp/cps1_tile_tests
/tmp/cps1_tile_tests

# Synthetic Python interleaving and local-export tests
python3 -m unittest discover -s tests -v

# Switch (devkitPro/libnx switch-dev)
make -j2
```

The C decoder's bitplanes, row strides and MSB-first 4bpp pixel indexing
are the same as the earlier independently exercised Python reference
in `tools/cps1_tiles.py`. All test data in GitHub is synthetic.

**Validation scope:** GitHub Actions confirms cross-compilation and tests
after a successful run. This does not imply physical console boot or
gameplay validation; actual Switch controls and SD path must still be
tested on a development-enabled device.

## Future development

This is a diagnostic stepping stone toward rendering actual CPS-1 scene
layers, authentic palettes and HD-restored sprites directly on Switch.
A synchronized MAME RAM capture and parity comparison remain pending.

# Stage296 — decode actual MAME 0.106 packed-indexed MNG frames

## Evidence triggering this change

The Stage295 [real historical Windows MAME synthetic run](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39667543711)
verified the exact artificial Minivader ROM, recorded a synthetic input
file, replayed it with **exit code 0**, and wrote an MNG plus **24**
consecutive INP-read counter CSV rows with callback indices 10–33.

The diagnostic result was `BLOCKED_SYNTHETIC_MNG_DECODING` despite MNG
and trace file creation. Thus the next discrepancy is in the independent
video decoder, not proof that the video was never written.

Historical MAME 0.106 `src/png.c:png_create_datastream` selects indexed
PNG (color type 3) when the emulated bitmap is 16-bit with no more than
256 palette colors. It uses **1, 2, 4 or 8 bits** per palette entry
depending on the actual used palette size and packs pixel indices into
MSB-first bytes. Our prior PNG integrity checker assumed **all** PNGs
had 8 bits per pixel channel, even indexed PNG. The synthetic Minivader
game has only two palette colors, making 1-bit frames a plausible
cause of the decoder's rejection.

## New decoder behavior

- Allow exactly 1-, 2-, 4-, or 8-bit **indexed** PNG with color type 3.
  Other supported PNG color types still require 8-bit samples.
- Validate the palette against the bit-depth capacity; continue checking
  CRCs, chunk ordering, IDAT zlib bounds, dimensions and scanline filters.
- Compute packed row size as ceil(width × bits_per_index / 8).
  Defilter the **encoded row bytes** before extracting palette indices.
- Expand packed pixels MSB first, ignoring end-of-row pad bits, and
  produce the same uncomposited RGBA8 output used by the existing
  video overlap checker. Continue rejecting transparency chunks.
- Keep all private game pixels and original game inputs outside GitHub.

Tests construct new miniature **synthetic** PNGs with 1, 2, 4, and 8
bits per index, odd widths, Sub and Up PNG scanline filtering,
malformed palettes, and a two-frame private MNG. Tests are ROM-free
and do not require any original game data.

## Actual MAME test

The Windows workflow additionally repeats Stage295's source-pinned
historical MAME test, using only an artificial Z80 Minivader ROM
created after the real production binary was uploaded. It will
attempt to validate the **actual MNG file from the real emulator**
using this updated decoder, then check the 24 callback counter rows.

A successful MNG decoder test still does **not** authenticate real
WolfMAME or original Cadillacs and Dinosaurs gameplay. The original
dino ROM/INP/WLF are still required for the private original-game
experiment, and all MNGs and trace bytes must remain off GitHub.

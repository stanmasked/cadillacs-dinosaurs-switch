# CPS-1 composite sprite ROM-bank rollover — Stage 31

## Specific confirmed renderer discrepancy

In MAME, `cps_state::cps1_render_sprites` first calls
`gfxrom_bank_mapper(GFXTYPE_SPRITES, original_code)` to validate and
translate the original buffered OBJ code. For each 16x16 constituent
of a 2D composite sprite it then calculates a new code:

```text
(code & ~0x0f) + ((code + composite_col) & 0x0f)
               + 0x10 * composite_row
```

The MAME gfx drawing method `gfx_element::prio_transpen` then executes
`code %= elements()` before reading the graphics tiles. For a dino
4,194,304-byte graphics region there are 32,768 16x16 entries.

**The old Python and C implementations erroneously rejected individual
composite parts with calculated code >=32768.** Thus a valid composite
sprite starting at code `0x7ff0` and extending one additional 16-pixel
row did not display the wrapped piece that MAME reads from tile 0.

This is separate from the previous sprite-priority correction in PR #15.

## Change

- Python `tools/cps1_frame.py`: keep the original OBJ base-code mapping
  check, then wrap each composite part modulo the available `16x16`
  tile count before decoding it.
- Nintendo Switch portable C `source/cps1_scene.c`: reject invalid
  original base codes (>=32768) **before** expanding any parts, and
  wrap valid constituent codes with `code %= CPS1_TILE16_COUNT`
  inside the tile draw function.
- Preserve CPS-1's nibble-wrapped horizontal tile arithmetic,
  part positioning, flip flags and first-sprite-wins priority policy.

The distinction between raw base validation and composite-part wrapping
is important: blindly applying modulo to an invalid original base code
would create **new sprites that do not exist in MAME**.

## Regression tests

Seven new ROM-free Python tests in
`tests/test_cps1_composite_sprite_rom_wrap.py` exercise:

1. The 4 MiB / 128 bytes = 32768 16x16 tile boundary.
2. The second row of a valid vertical composite mapping to code 0.
3. Vertical flipping across that boundary.
4. Invalid original code `0x8000` remaining invisible.
5. Horizontal flipping selecting codes `0x7ff1` / `0x7ff0`.
6. A 2x2 composite with both flips, including an **opaque pen zero**
   in the wrapped upper-left cell.
7. Metadata preserving raw intermediate code `0x8000` until the gfx
   drawing step (matching MAME's responsibility split).

In a local isolated fixture, these 7 checks plus 7 retained sprite
priority tests passed: **14/14**. Test graphics are artificially
generated, never copied from the game.

Three added native `tests/test_cps1_scene_native.py` cases exercise C/Python
parity for vertical wrapping, vertical flipping, and an invalid base
sprite. Their execution depends on compiling the actual portable
C source; **these native integration cases are not yet claimed passed**
until a complete native test execution is available.

## Existing binaries and limitations

This PR branches from, and **depends on PR #15**. It is not a standalone
replacement for that correction. The latest previously verified Switch
binary **v0.5** predates both changes, so loading that binary cannot
confirm either fix.

Neither a synthetic 16x16 pixel result nor a passing local unit test
establishes exact real gameplay frame parity. Running actual MAME
and a new on-console NRO remains outstanding.

Upstream reference:

- `src/mame/capcom/cps1_v.cpp` — `cps1_render_sprites` and
  `gfxrom_bank_mapper`
- `src/emu/drawgfx.cpp` — `gfx_element::prio_transpen`

These files are available at
https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp
and https://github.com/mamedev/mame/blob/master/src/emu/drawgfx.cpp.

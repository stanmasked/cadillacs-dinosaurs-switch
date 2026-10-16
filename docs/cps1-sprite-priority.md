# CPS-1 Sprite Pixel Priority — Native/Python Fix

## Confirmed discrepancy with MAME

In the CPS-1 renderer for Cadillacs and Dinosaurs (`dino`), MAME visits
normal buffered OBJ entries **first to last**. Its
`gfx_element::prio_transpen` (`src/emu/drawgfx.cpp`) uses
`PIXEL_OP_REBASE_TRANSPEN_PRIORITY` (`src/emu/drawgfxt.ipp`).
For a nontransparent pen the macro checks the incoming priority bitmap;
if not masked, it writes the pixel. **Regardless of whether the pixel
was masked**, it stamps priority 31. Subsequent sprite pixels at the
same position cannot replace the first one.

The original project's Python and portable C implementations previously
traversed the correct object order, but failed to mark the priority
bitmap after a sprite pixel. This made **later sprites appear in front**.

## Correction

`tools/cps1_frame.py` and `source/cps1_scene.c` now both:

1. Skip the transparent pen 15 **without changing priority**.
2. If a nontransparent sprite pen is not blocked, draw its color.
3. Always mark the pixel as occupied by a sprite, even if an earlier
   high-priority scroll mask blocked its color.

This is a targeted change: original ROM decoding, file formats,
palette layout, layer order, camera coordinates, sprite animation
metadata and Nintendo Switch input handling are unchanged.

## Tests

`tests/test_cps1_sprite_priority.py` adds six **ROM-free** Python
tests for first-opaque-wins, reversed order, transparency, pen 0,
scroll mask and OBJ end-of-list marker. All six passed locally; the new full-viewport regression is committed but awaits local execution.

Three new `NativeSceneTests` cases in
`tests/test_cps1_scene_native.py` compile the actual C renderer and
compare it pixel-for-pixel with Python for overlapping, transparent
and pen-zero sprite pairs. These were **committed** but their execution
must be confirmed separately; GitHub Actions has been failing before
jobs execute.

A full-sized 384x224 synthetic test scene with two exactly overlapping
16x16 opaque sprites was rendered using the **old and corrected Python
implementations**. Exactly **256 of 86,016** output pixels changed.
The previous output showed the later sprite (RGB 30,220,70);
the corrected output shows the earlier sprite (RGB 230,20,30).

All test tile graphics are synthetic: no MAME game screenshot, extracted
artwork, original ROM or private snapshot is committed in this change.

## Remaining accuracy work

MAME still needs to run for a full synchronized gameplay capture before
claiming **actual first-level or pixel-perfect CPS-1 parity**.
Console compilation and on-hardware execution of the changed C source
are also unverified at this stage. The last confirmed `.nro` remains
v0.5 and **does not contain this code change**.

Source references:

- MAME CPS-1 sprite traversal:
  https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp
- MAME `gfx_element::prio_transpen`:
  https://github.com/mamedev/mame/blob/master/src/emu/drawgfx.cpp
- Original priority pixel macro:
  https://github.com/mamedev/mame/blob/master/src/emu/drawgfxt.ipp

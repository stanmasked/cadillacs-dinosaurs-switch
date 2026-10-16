# CPS-1 priority bitmap persistence across multiple sprite slots — Stage 33

## MAME source-level finding

The original CPS-1 renderer supports four programmable draw slots, each
selecting a background tilemap or the OBJ sprite list. Although a typical
scene uses each layer once, the hardware layer control can select the same
layer (including OBJ) in multiple slots.

MAME's `cps_state::render_layers` in
`src/mame/capcom/cps1_v.cpp` calls:

```cpp
screen.priority().fill(0, cliprect);
```

**once** at the start of the frame, *before* iterating draw slots.
When a sprite slot follows a tilemap, MAME draws the tilemap's
foreground priority pens with priority code 1 into the existing
priority bitmap; it does not clear the bitmap.

MAME `src/emu/tilemap.cpp` uses
`pri[i] = (pri[i] & (pcode >> 8)) | pcode`.
The default tilemap `priority_mask=0xff` (from `tilemap.h`) and
foreground `priority=1` therefore yield a **bitwise OR** update.
MAME `src/emu/drawgfxt.ipp` stamps priority 31 for every
nontransparent OBJ pixel, even if a previous foreground priority bit
prevented the pixel from being written.

## Confirmed discrepancy

Our Python compositor and native C renderer allocated an initially
zeroed priority map, **but incorrectly cleared it again before every
sprite slot**. They also *assigned* background priority flags, which
could erase priority left by earlier OBJ draws.

For draw slots `[Scroll2, OBJ, Scroll1, OBJ]`, a sprite was drawn
in the first OBJ pass, then hidden by Scroll1, then erroneously redrawn
**on top of Scroll1** by the second OBJ pass.

The corrected behavior leaves the Scroll1 pixel visible. Both engines
now clear once per frame and only add foreground priority bits without
erasing previous sprite ownership.

The affected order is a source-level edge case; **we do not claim it
has been observed in the actual first-level MAME capture**.

## Change

- `tools/cps1_frame.py`: retain the single initially zeroed
  `sprite_occlusion` map for all four draw slots. Only set an
  occlusion bit when a background high pen matches the CPS-B mask.
  Never reset or clear it before a subsequent OBJ pass.
- `source/cps1_scene.c`: remove the inter-slot `memset` and
  replace the high-layer priority assignment with monotonic
  set-if-masked logic. The initial `calloc` already corresponds
  to MAME's one frame-start `fill(0)`.
- The prior first-opaque-sprite-wins, sprite ROM wrap and scroll order
  implementations remain otherwise unchanged.

## Regression evidence

The standalone Python test `tests/test_cps1_multiple_obj_passes.py`
includes five ROM-free assertions for a late foreground under a repeated
OBJ pass, a later transparent front layer, an ordinary single OBJ pass,
priority masking, and disabled backgrounds.

Three additional native C/Python tests in
`tests/test_cps1_scene_native.py` check full 384×224 RGBA parity for
the two edge-case arrangements and an unchanged ordinary single pass.

A portable C host stand reconstructed from the earlier PR #16 source
was modified with these same changes, compiled with GCC
`-Werror` and UBSan, and exercised against Python on **35/35**
ROM-free local tests (25 retained + 5 new native comparisons with 12
deterministic frame variations + 5 standalone Python tests). Every
tested full-frame comparison was byte-identical. The local stand is
not a byte-exact fetched GitHub checkout.

Before the fix, a representative synthetic viewport pixel was
`(230, 20, 30, 255)` (incorrect OBJ red). After the fix it becomes
`(15, 25, 220, 255)` (correct foreground blue).

GitHub Actions has consistently failed before job steps; the
newly committed GitHub integration suite is **not independently
confirmed by the remote CI**. This PR remains draft and is stacked
on PR #17 → #16 → #15. No original game ROMs, extracted tiles,
captured gameplay, or Nintendo Switch binary are published.

## Still not verified

MAME original first-level render-pass captures, source-level
fidelity of all masks and corner cases, Switch NRO compilation,
physical Nintendo Switch testing, and actual game logic.

Source links:
- https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp
- https://github.com/mamedev/mame/blob/master/src/emu/tilemap.cpp
- https://github.com/mamedev/mame/blob/master/src/emu/tilemap.h
- https://github.com/mamedev/mame/blob/master/src/emu/drawgfxt.ipp

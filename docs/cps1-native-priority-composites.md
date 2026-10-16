# Stage 32 — Native CPS-1 composite sprites under scroll priority masks

This stage **tests** the renderer corrections from stacked PRs #15
(first-opaque-sprite-wins priority) and #16 (composite tile-bank rollover)
under real C compilation and synthetic full-frame overlap scenarios.
No ROM, copyrighted art, screenshot or captured gameplay is included.

## Verified behavior, referenced from MAME

- MAME `render_layers` renders low-priority foreground
  `TILEMAP_DRAW_LAYER1`, then a special front mask
  `TILEMAP_DRAW_LAYER0` when the following slot contains sprites.
- The front mask uses the **priority pen register** for the tile's
  priority group; the foreground's transparent pen 15 must not block.
- MAME's `PIXEL_OP_REBASE_TRANSPEN_PRIORITY` stamps priority 31 for
  *every nontransparent* sprite pixel, even when that pixel was blocked
  by a higher-priority background mask.
- In composite sprites, an original code must first be accepted by
  the CD63B mapper. Constituent tile codes wrap modulo 32768, and
  their individual horizontal and vertical flips are applied before
  transparency/priority checks.

## Locally compiled C and Python testing

A portable local stand was assembled from the source behavior in
PR #16 and compiled using:

```sh
gcc -std=c11 -O2 -Wall -Wextra -Werror \
  -fsanitize=undefined -fno-sanitize-recover=all \
  -fPIC -shared -Isource \
  source/cps1_scene.c source/cps1_tile.c -o libcps1scene.so
```

The C code was reconstructed from the retrieved GitHub sources in
this local stand; it is **not a verified byte-for-byte checkout** of
the PR. An independent GitHub checkout test is still required.

The stand compared **each complete 384×224 RGBA frame byte-for-byte**
against the Python renderer, using synthetic 4 MiB graphics in memory.
All tests passed:

- 7 previous composite bank wrapping tests
- 7 previous sprite priority tests
- 11 new local native C/Python test cases, including eight seeded
  scroll/priority variations within one case.

**25/25 local tests passed, zero C/Python pixel mismatches** in these
scenarios. The C build passed gcc warnings-as-errors and ran with UBSan.

## GitHub tests

Five new native `NativeSceneTests` are committed in
`tests/test_cps1_scene_native.py`:

1. Scroll2 front-pen mask over two composite rows.
2. The same composite with front mask disabled and sprite pixel
   priority preserved (including **opaque pen0** in the second row).
3. Only the actual CPS-B priority group controls front masking.
4. A fully transparent foreground tile enables sprite visibility at
   its coordinates but not at the next tile row.
5. Sixteen fixed-seed combinations of per-tile group assignment,
   registers, scroll coordinates and flipped composites.

These GitHub tests **have not been independently executed** against
a clean fetched PR checkout because CI continues to fail before
the job begins. No new NRO has been compiled or run on Switch.

## Unverified gameplay

A successful C/Python comparison is an implementation consistency
check, not proof that either matches MAME's actual original frames.
The first original game stage, live MAME frame capture, hardware
flipscreen, exact raster events and on-console rendering remain
unverified.

MAME upstream references:

- https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp
- https://github.com/mamedev/mame/blob/master/src/emu/drawgfxt.ipp

# Stage 34 — CPS-1 global flipscreen bit15 in Python and native C

## Confirmed missing rendering feature

On original CPS-1 hardware, **CPS-A VIDEO_CONTROL bit 15** switches
global screen flip. In MAME:

- `cps_state::screen_update_cps1` calls `flip_screen_set(BIT(videocontrol,15))`.
- `driver_device::flip_screen_set` invokes `updateflip()`, which sets
  `TILEMAP_FLIPX | TILEMAP_FLIPY` on every tilemap.
- `cps1_render_sprites` mirrors an OBJ tile's position using
  `512 - 16 - x`, `256 - 16 - y` and reverses its flip flags.

Our older renderers supported *individual* OBJ flip flags but ignored
the global CPS-A bit entirely, leading to incorrect frame orientation
when flip mode was active.

## Implementation

The fully visible native CPS-1 viewport is **X=64..447**, **Y=16..239**.
These bounds map exactly onto themselves under physical raster
coordinates `x' = 511 - x`, `y' = 255 - y`.

Both partial renderers now support global bit15 by compositing the
normal frame—including all sprite priority masks, constituent
sprite flips and Scroll2 line scroll—and mirroring RGBA output over
this physical raster center.

- Native C: `source/cps1_scene.c` rotates its 384×224 result 180
  degrees by swapping RGBA pixels in-place after all layers are drawn.
  No extra full-frame allocation or change to the CPS1SCN1 format.
- Python: `tools/cps1_frame.py` clears bit15 in a **local shallow
  copy** of the snapshot, renders the *physically mirrored source
  viewport*, then reverses its RGBA pixel sequence. This respects
  cropped inspection views (e.g. a crop at X=420,Y=206 corresponds to
  unflipped source X=68,Y=32), rather than incorrectly rotating a
  crop about its own center.
- Pixel data, actual input snapshot and original game art remain
  unchanged.

The Python renderer refuses flipped crop ranges that extend past the
512×256 hardware raster rather than sampling outside defined bounds.

## Local verification

A ROM-free portable C test stand assembled using the Stage 33
C/Python source was compiled with GCC `-std=c11 -O2 -Wall -Wextra
-Werror -fsanitize=undefined`. All **53 of 53** unit tests passed.

Seven new test cases cover non-symmetric sprite placement, composite
blocks, masked Scroll2 foreground, duplicate OBJ passes, Scroll2
rowscroll, transparent backgrounds and hardware-coordinate crop
semantics. All tested 384×224 native C output matched Python
**byte-for-byte**, and flipped output matched a full 180-degree
pixel transform of the normal-mode scene.

Five additional native C/Python test methods have been **committed**
into `tests/test_cps1_scene_native.py` on this PR branch. Execution
of those exact GitHub-hosted tests still requires a working
GitHub Actions runner.

**Accuracy limits:** Source-level MAME behavior supports the 180-degree
transform, but a real CPS-1 first-level frame and MAME's exact raster
output have not been captured and compared yet. This code is not a
new NRO, does not add game logic or other unimplemented CPS-1 features
(stars, subframe raster events), and has not been run on Switch.

## Review dependencies

This is a **stacked draft PR** based on PR #18, which depends on
#17 → #16 → #15. Merge/rebuild only once all source changes and tests
are verified. The last confirmed v0.5 Switch binary does **not** include
the new global flip or earlier sprite corrections.

## Upstream references

- [MAME cps1_v.cpp](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp)
- [MAME driver.cpp](https://github.com/mamedev/mame/blob/master/src/emu/driver.cpp)
- [MAME tilemap.cpp](https://github.com/mamedev/mame/blob/master/src/emu/tilemap.cpp)

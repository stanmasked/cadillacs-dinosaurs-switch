# Cadillacs and Dinosaurs — Nintendo Switch HD Remake

Target: **Capcom CPS-1, World 930201, MAME dino**.

## Current status
Initial Switch homebrew bootstrap and ROM auditing framework. **Not yet playable.** No original commercial assets are stored here.

## Build
Install [devkitPro switch-dev](https://www.switchbrew.org/wiki/Setting_up_Development_Environment), export DEVKITPRO, then run `make`. Expected result: `cadillacs-dinosaurs-switch.nro`. Switch compilation is not yet verified.

## ROM audit
Run `python3 tools/verify_rom.py /path/to/your/dino.zip` using your own legitimately acquired files. Never commit ROM data.

## Milestones
1. Audit original CPS-1 ROMs and establish gameplay references.
2. Create a deterministic gameplay-faithful runtime baseline.
3. Implement Switch video, audio and local controllers.
4. Restore HD sprites, stages, interface and effects.
5. Test co-op, performance, levels and original input timing.

## Intellectual property
Cadillacs and Dinosaurs belongs to its respective owners. Distribution of original assets or a public IP-based remake requires appropriate rights.
## Graphics research (work in progress)

The CPS-1 4bpp decoder supports `8x8-left`, `8x8-right`, `16x16`, and `32x32`.
Generate **local-only** diagnostic tile sheets from your own parent `dino.zip`:

```sh
python3 -m unittest discover -s tests -v
python3 tools/cps1_tiles.py /path/to/dino.zip --layout 16x16 --start 0 --count 128 --columns 16 --scale 2 --out local_outputs/tiles16.png
```

Generated images use grayscale placeholders for 4bpp pixel indices; they are not authentic game colors. Correct palette selection requires runtime palette RAM. See [tile decoder technical notes](docs/cps1-tile-decoder.md). The test suite uses synthetic ROM fixtures and **does not require or fetch commercial game data**.

## CPS-1 palette and tile bank research

World 930201 uses MAME's `CPS_B_21_QS2` and `CD63B` video configuration. The project now contains:

- `tools/cps1_video.py` — exact CPS-1 16-bit palette-color formula, six-page palette-copy control, CD63B tile bank mapping and composite sprite-code expansion.
- `tools/cps1_color_atlas.py` — creates a **local-only** color PNG from user-owned `dino.zip` plus a **runtime gfx RAM palette snapshot**. The ROM alone does not contain sufficient data to infer the palette active during gameplay.
- `tests/test_cps1_video.py` — synthetic unit tests for palette, graphics mapping, sprites and PNG output.

Full commands, input format and limitations: [CPS-1 video/palette research](docs/cps1-video-palette.md).

```sh
python3 -m unittest discover -s tests -v
python3 tools/cps1_color_atlas.py /private/dino.zip /private/palette_snapshot.json \
  --layer sprites --color 0 --count 32 --out local_outputs/sprites_color.png
```

**Verified locally:** 34/34 Python tests on Python 3.13; graphics mapping and color atlas export also exercised with the user-provided parent ROM and deliberately artificial palette. **Not yet verified:** GitHub Actions run, playable native Switch build, authentic RAM-derived palette, gameplay rendering.


## Frame composition from captured CPS-1 video RAM

`tools/cps1_frame.py` is now a **partial offline compositor** for `dino`:
three 64×64 tilemap RAM scanners, CPS-B layer order, palette/color groups,
already-buffered OBJ sprite RAM, block-sprite flips, and the hardware
384×224 visible viewport. It does not capture memory from an emulator
itself and is **not pixel-perfect** (priority masks, line scrolling,
flipscreen and several other effects remain unimplemented).

To replay an actual game frame you must supply a **local runtime RAM
snapshot** along with your own ROM. There are no real game-state
snapshots in the repository. See [snapshot schema and known limitations](docs/cps1-frame-compositor.md).

```sh
python3 -m unittest discover -s tests -v
python3 tools/cps1_frame.py /private/dino.zip /private/frame_snapshot.json \
  --out local_outputs/partial_frame.png
```

Validation: **50/50 Python tests passed locally**. The renderer also
produced a 384×224 PNG using real ROM pixel data with **synthetic test
VRAM and synthetic palette**, which is *not a game screenshot*.
Nintendo Switch compilation and GitHub Actions execution remain unverified.

## QS2 frame replay — raster / priority / capture conversion

A local raw-dump adapter `tools/cps1_capture.py` converts **coherent MAME/CPS-1 RAM and register dumps** into the replay JSON. It requires 0x40000 bytes of graphics RAM, 0x40 bytes each of CPS-A/CPS-B registers, and 0x800 bytes of **buffered** sprite OBJ RAM; the original `dino.zip` is only needed for the subsequent private frame rendering step. Native-game RAM capture is not yet automated.

The frame renderer now accepts `priority_masks`, `video_control`, `rowscroll`, and `rowscroll_offset` to model CD63B sprite occlusion and per-scanline Scroll2 scrolling. A separate effective palette RAM capture is necessary for *authentic* colors; otherwise the adapter explicitly labels the current source-palette estimate as approximate.

See [raw capture workflow and exact register mappings](docs/cps1-capture-and-raster.md).

Local validation: **68/68 Python tests passed** and a 384×224 diagnostic frame was reconstructed from *synthetic* raw RAM dumps plus the locally supplied real `dino.zip` graphics. The resulting scene is not an original gameplay frame.

A dedicated [Switch native bootstrap workflow](.github/workflows/switch-bootstrap.yml) now attempts a **ROM-free** `.nro` build in the official devkitPro devkitA64 container. Its CI outcome and real-console runtime remain unverified.

## Verified Switch NRO bootstrap and frame parity QA (2026-10-16)

The `Makefile` follows the canonical devkitPro/libnx application layout.
The private-repo pull-request CI executed in `devkitpro/devkita64:20260219`
and **successfully built and uploaded a valid native Switch NRO**:

- [NRO build run #38929163586](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/38929163586) — SUCCESS, artifact `cadillacs-dinosaurs-switch-bootstrap`. Verified `NRO0` header at offset `0x10`, file size **166,085 bytes**, SHA-256 `ef682e60afb7f1d7ba79b04b2368e5239926d330e65f2cca4eec3fbdefd47093`.
- [Python test run #38929164566](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/38929164566) — SUCCESS, **77 tests** including nine new reference-frame comparator tests.

`tools/frame_compare.py` reads two same-size RGBA PNG frames, counts
pixel/color differences, and optionally saves a red-channel error heatmap.
Usage and capture requirements: [Pixel-exact frame QA](docs/frame-parity-testing.md).

```sh
python3 tools/frame_compare.py /private/mame_reference.png \
  /private/cps1_reconstruction.png \
  --diff local_outputs/pixel_error.png
```

**Important:** The NRO is a ROM-free **technical bootstrap**, not yet a playable
game. Native compilation and output format are confirmed; real Switch hardware
boot and gameplay functionality are not tested. A real MAME reference frame
has not been captured, so there is no pixel-parity claim for the actual game.

## Native Nintendo Switch graphics inspector — v0.2

The ROM-free NRO now renders a **native 1280×720 interactive grid** of
actual CPS-1 16×16 graphics tiles when a local, user-provided `gfx.bin`
is available on SD. These are grayscale palette-index previews, **not**
restored HD images, gameplay, or authentic in-game colors. If the asset
is missing, the app explains the required path and exits with PLUS.

```sh
# On a computer: assemble a 4 MiB region from your own parent ROM set
python3 tools/cps1_gfx.py /private/dino.zip --out-local gfx.bin

# On Switch SD card: place the binary at
# sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin

# ROM-free local regression tests
python3 -m unittest discover -s tests -v
gcc -std=c11 -O2 -Wall -Wextra -Werror -Isource \
 tests/cps1_tile_native_test.c source/cps1_tile.c -o /tmp/cps1_tile_tests
/tmp/cps1_tile_tests
```

Detailed installation, navigation and limitations: [Switch tile inspector](docs/switch-tile-inspector.md).

**Never commit gfx.bin, game ROMs or derived copyrighted assets.**

## Nintendo Switch v0.3 — native partial scene replay

Switch now has a **native C frame compositor** (not just a tile-sheet viewer).
It optionally reads a local `scene.bin` snapshot alongside the owner's
`gfx.bin`, reconstructs three CPS-1 background layers, sprites, effective
palette RGB, QS2 priority pens and Scroll2 scanline scrolling into a
**384×224** static scene, and presents it at **3× nearest-neighbor scale**
on the Switch framebuffer. Press **X** to toggle the scene; existing
tile browsing still works without a snapshot.

The compact binary scene format uses magic `CPS1SCN1`, a strict size
and CRC32; its exporter requires **effective runtime palette RAM**, not
a guessed ROM palette. Details: [installation and capture format](docs/switch-native-scene-v03.md).

```sh
python3 tools/cps1_scene_export.py /private/frame_snapshot.json --out scene.bin
# SD: switch/cadillacs-dinosaurs-switch/gfx.bin
# SD: switch/cadillacs-dinosaurs-switch/scene.bin
```

No ROM or private RAM capture is uploaded to GitHub. Synthetic automated
tests compare native C-composed pixels to the Python reference. This is
**static frame replay, not interactive gameplay, HD-restored graphics, or
confirmed pixel parity with a real MAME frame**.

## Native Switch v0.4 — interactive scene camera

The local-only scene inspector supports manual **on-device camera panning**
of three background tilemaps. In scene mode press D-pad to scroll, hold ZR
to pan faster, press A to reset to the original captured scroll values, and
press X to return to tile browsing. Backgrounds are re-rendered natively
from 4-bit CPS-1 graphics; sprite coordinates and palette state remain
those of the captured frame.

The `scene.bin` format and required local `gfx.bin` are **unchanged**.
No additional commercial assets are included in the ROM-free NRO.
Details and limitations: [Interactive scene inspection v0.4](docs/switch-interactive-scene-v04.md).

This is a developer camera test, **not movement/gameplay of characters**.
CI exercises native-vs-Python pixel equality, 16-bit wrap and scroll reset;
real console testing and synchronized MAME frame capture remain pending.

## Nintendo Switch v0.5: native frame sequence player

An optional private `sequence.bin` now provides a **bounded 1–120-frame
timeline** of existing `CPS1SCN1` snapshots. The native C renderer plays
back the sequence using a real timer with a 60 Hz virtual tick clock,
rather than incorrectly assuming that one display iteration is one
game frame. It supports pause, previous/next frame, and 0.5×/1×/2× speed.

```sh
# Purely synthetic, ROM-free animation test from generated state snapshots:
python3 tools/cps1_sequence_export.py --demo --fps 12 --out sequence.bin

# Alternatively, pack your own *synchronized* authorized CPS-1 capture JSONs:
python3 tools/cps1_sequence_export.py \
    --frames-dir /private/captured-frames --fps 12 --out sequence.bin
```

Copy sequence.bin next to your privately created gfx.bin on Switch SD.
If sequence.bin is unavailable or invalid, v0.4's optional static
scene.bin and tile inspector remain available. See
[full installation, format, controls, and limitations](docs/switch-sequence-v05.md).

**This is diagnostic motion of independent static captures, not original
game execution, character animation restoration, or real-time gameplay.**
No commercial assets are embedded in the GitHub build.

## Experimental MAME reference capture — live-data bridge

The next graphics-fidelity milestone is **authentic CPS-1 reference pixels**,
not another synthetic demonstration. Added:

- `tools/mame_cps1_capture.lua`: runs through MAME's documented
  `-autoboot_script` interface and samples real **384×224 RGB frames**,
  effective 3072-color palette, CPS-A/B registers, and the QSound board's
  **0x30000-byte** mapped graphics RAM. The Lua script has not yet been
  tested in a running MAME session.
- `tools/mame_capture_import.py`: validates lengths/endian/map boundaries
  and converts native MAME RGB bytes into a lossless reference PNG and
  **explicitly partial** register/VRAM snapshot.
- A safety guard in `tools/cps1_scene_export.py` blocks promoting partial
  captures to native Switch `scene.bin` without VBlank-latched OBJ.

See [MAME reference capture instructions and limitations](docs/mame-live-reference-capture.md).

```sh
mkdir -p cps1-captures
mame dino -rompath /private/mame-roms \
    -autoboot_script /path/to/tools/mame_cps1_capture.lua
python3 tools/mame_capture_import.py cps1-captures frame-00000900 \
    --out-dir local_outputs/mame-reference
```

**Important:** Real captured MAME frames do not yet exist in this
repository or test environment. The Lua capture cannot access the
driver's VBlank-latched sprite buffer; incomplete replays are not
pixel-parity eligible. Original data and derived frames stay local.

## Experimental MAME VBlank-latched sprite capture

An optional *source patch generator* captures MAME's real
`m_buffered_obj` immediately after the CPS-1 VBlank copy. This 0x800-byte
buffer is the input used by MAME's sprite renderer and cannot reliably be
recovered from current GFX RAM at arbitrary moments.

- `tools/mame_obj_instrument.py`: generate a patch against a **local**
  MAME CPS-1 driver source file, with bounded frame-number capture.
- `tools/mame_obj_validate.py`: check resulting 2048-byte big-endian
  latched OBJ buffers, SHA-256 and sprite list marker.
- `tests/test_mame_obj_capture.py`: no-ROM C++17 compiled latch smoke test
  and synthetic file validation.

See [MAME VBlank OBJ instrumentation instructions](docs/mame-vblank-obj-instrumentation.md).
The patch has **not** been compiled with full MAME or exercised on the
original game. Screenshots and object latches may refer to different
render phases; resulting dumps remain **not pixel-parity eligible** until
their frame synchronization is independently established.

No original ROM, MAME source or captured sprite data is committed.

## Preferred experimental capture: same render callback

The new [render-pass capture guide](docs/mame-render-pass-capture.md)
describes a stronger successor to the separate VBlank OBJ dump:
`tools/mame_render_instrument.py` creates an opt-in patch that captures
the original CPS-1 RGB image, effective palette, 192 KiB GFX RAM,
CPS-A/B registers and the actual `m_buffered_obj` **inside one
screen_update_cps1 invocation, immediately after render_layers**.

`tools/mame_render_import.py` checks the complete 7-file contract
and produces a private reference PNG plus an OBJ-populated scene JSON
ready to **attempt** a pixel comparison with the Switch-oriented Python
renderer. The importer always records
`pixel_parity_verified: false`: it does not claim that reconstructed
pixels already match MAME.

The source anchor was checked against upstream MAME CPS-1 video blob
`c1b5e3867824d0d1877b981142db7741346d2c55`.
If MAME draws using partial update rectangles rather than the whole
384x224 view, the experimental collector **does not save a frame**;
it refuses to combine separate render phases into a misleading snapshot.

The host C++-compilation test and Python data-contract tests are
synthetic only; full MAME instrumented execution is still pending.
No original ROMs, captured memory, frames or assets are committed.

## Quantitative pixel matching against a genuine MAME frame

Added `tools/mame_frame_parity.py` to link **same-render callback**
MAME dumps, the existing independent CPS-1 Python renderer and
pixel-exact RGBA comparison in one locally runnable command:

```sh
python3 tools/mame_frame_parity.py /private/dino.zip \
    /private/cps1-render frame-00000900 \
    --out-dir /private/cps1-parity --require-exact
```

It produces both 384x224 PNGs, an absolute-error heatmap and
a machine-readable parity report with number/percentage of mismatches,
color errors and SHA-256. A strict flag distinguishes *identical* from
*not identical* and malformed input without suppressing the report.
All reports say game-wide accuracy and physical Switch testing are
**not verified**. No real MAME gameplay frame has yet been captured or
compared in this environment. Five new ROM-free end-to-end tests exercise
exact matches and deliberate single-pixel defects.
See [render-pass capture instructions](docs/mame-render-pass-capture.md).

## v1.3 research diagnostics — spatial parity report

Pixel comparison now includes scanline and column histograms, a precise
mismatch bounding rectangle, top-left/top-right/bottom-left/bottom-right
counts and separate R/G/B channel errors. Use these to locate errors in
sprites, backgrounds, scroll timing and effective palette colors, rather
than relying solely on a global percentage.

`tools/frame_error_profile.py` is a deterministic dependency-free helper;
its five new synthetic tests and the end-to-end frame tests verify error
positions and empty frames. See
[render-pass capture and spatial error report](docs/mame-render-pass-capture.md).

These checks do not require a game ROM and establish no real MAME frame
parity. Real original-frame capture and Switch console execution remain
unverified.

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

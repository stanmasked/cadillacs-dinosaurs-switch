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

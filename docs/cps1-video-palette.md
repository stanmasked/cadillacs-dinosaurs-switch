# World 930201: CPS-1 palette, graphics bank mapping and sprite blocks

Reference: [MAME CPS-1 video driver](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp), including `cps1_build_palette`, `gfxrom_bank_mapper`, `get_tile0_info` and `cps1_render_sprites`. Reference inspected at upstream blob SHA `c1b5e3867824d0d1877b981142db7741346d2c55`.

## Game-specific board setup

The configuration row for `dino` (World 930201) uses `CPS_B_21_QS2` and the `CD63B` graphics mapper. The CD63B PAL defines **two 0x8000-code-unit banks**, mapping all four graphic types over range 0x0000..0xffff (after the MAME type-specific shift).

| Layer | MAME code shift | Highest accepted raw tile code |
| --- | ---: | ---: |
| Sprites | 1 | 0x7fff |
| Scroll1 (8x8) | 0 | 0xffff |
| Scroll2 (16x16) | 1 | 0x7fff |
| Scroll3 (32x32) | 3 | 0x1fff |

The two-bank lookup returns the same valid raw code for this particular board. Other CPS-1 boards have different mappings; this module deliberately supports **CD63B only**. Invalid requests return -1 (transparent placeholder in the offline exporter).

The 8x8 Scroll1 tiles have two graphic views (`8x8-left`, `8x8-right`). **Tilemap index bit 5**, rather than sprite code, selects the view in MAME. A standalone tile atlas can select either view using `--scroll1-half left|right` but cannot automatically reconstruct an authentic tilemap without its RAM snapshot.

## Color format and RAM pages

A 16-bit palette entry is `BBBB RRRR GGGG BBBB`, meaning **4 high bits of brightness**, then red, green and blue as four-bit values (brightness and blue have the same letter, but occupy separate nibbles).

For each color channel `channel4`, MAME's integer formula is:

```python
brightness = 15 + 2 * ((word >> 12) & 15)
channel8 = (channel4 * 17 * brightness) // 45
```

At max brightness, 15 becomes 255; at zero brightness, 15 becomes 85.

There are **6 palette pages** of `0x200` colors each (total **3072 palette entries**). Each page holds 32 color groups of 16 pens:

| Page | Type | Palette index base |
| --- | --- | --- |
| 0 | sprites | 0x000 |
| 1 | scroll1 | 0x200 |
| 2 | scroll2 | 0x400 |
| 3 | scroll3 | 0x600 |
| 4 | stars1 | 0x800 |
| 5 | stars2 | 0xa00 |

Palette page control is a six-bit mask. Disabled destination pages keep their earlier palette data. Source-page advancement follows the MAME CPS-1 behavior: **disabled pages before the first enabled one do not advance the source pointer**; disabled pages after it skip `0x200` source words.

For tiles and sprites, pen **15** is transparent in the color atlas. The correct RGB values *cannot* be recovered from the `dino.zip` static graphics region alone: games write palette words dynamically to graphics RAM, which the CPS-B chip copies to separate palette RAM.

## Local-only color tile export

Provide a local palette source snapshot, captured from a running game, as a JSON file:

```json
{
  "control": "0x3f",
  "words": ["0xf000", "0xff00", "0xf0f0"]
}
```

The short sample above illustrates **syntax only**. Real full-page exports need `0x200` 16-bit word values per copied page, and up to 3072 words for all six pages. The words must represent the **source gfx RAM palette** at the moment the palette-base register is written, not a packed PNG palette, BGR values, or arbitrary colors.

```sh
python3 -m unittest discover -s tests -v
python3 tools/cps1_color_atlas.py /private/dino.zip /private/palette_snapshot.json \
  --layer sprites --color 0 --first-code 0x200 --count 32 --columns 8 \
  --out local_outputs/sprites_reference.png
python3 tools/cps1_color_atlas.py /private/dino.zip /private/palette_snapshot.json \
  --layer scroll1 --scroll1-half right --count 32 \
  --out local_outputs/scroll1_right.png
```

The exporter writes a local RGBA PNG and never sends the ROM or extracted sprites to GitHub. Transparency, color groups and code mapping are applied, but tile/sprite attributes, scene composition, layer priority and in-game position require additional **RAM snapshots** before authentic gameplay frames can be recreated.

## Testing and scope

34 Python tests have passed locally on Python 3.13, including palette brightness/truncation, page-copy quirks, CD63B boundaries, composite sprite tile indexing/flips, left/right Scroll1 views, JSON palette parsing and exact PNG RGBA bytes on synthetic fixtures. The real user-provided `dino.zip` was also used for a local end-to-end export with an **artificial palette**, not authentic game colors. No ROM or extracted image is committed.

This phase does **not** implement gameplay emulation, audio, original palette extraction, a rendered in-game scene, HD asset restoration, or a Switch build.

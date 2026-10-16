#!/usr/bin/env python3
"""Reference-checked CPS-1/CD63B bank mapping, palette and sprite metadata.

Standalone Python without emulator dependencies or bundled ROM assets.
MAME reference: src/mame/capcom/cps1_v.cpp (dino -> CPS_B_21_QS2, CD63B).
"""
from dataclasses import dataclass
from typing import Sequence

PALETTE_PAGE_WORDS = 0x200
PALETTE_PAGES = 6
TOTAL_COLORS = PALETTE_PAGE_WORDS * PALETTE_PAGES
COLOR_GROUP_SIZE = 16
LAYER_PAGES = {
    'sprites': 0, 'scroll1': 1, 'scroll2': 2,
    'scroll3': 3, 'stars1': 4, 'stars2': 5,
}
MAPPER_SHIFTS = {'sprites': 1, 'scroll1': 0, 'scroll2': 1, 'scroll3': 3}


def decode_palette_word(word: int) -> tuple[int, int, int]:
    """MAME CPS-1 12-bit RGB plus 4-bit brightness, integer truncation."""
    if not isinstance(word, int) or not 0 <= word <= 0xffff:
        raise ValueError('Palette word must be an unsigned 16-bit integer')
    bright = 0x0f + ((word >> 12) * 2)
    return tuple(((word >> shift) & 0xf) * 0x11 * bright // 0x2d
                 for shift in (8, 4, 0))


def build_palette(words: Sequence[int], control: int,
                  previous: Sequence[tuple[int, int, int]] | None = None
                  ) -> list[tuple[int, int, int]]:
    """Copy enabled pages from graphics RAM, emulating CPS-1 palette control.

    Important: prior to the first enabled page, disabled pages do NOT advance
    the source pointer. Afterwards, disabled pages advance by 0x200 words.
    Skipped destination pages preserve previous palette RAM, if provided.
    """
    if not isinstance(control, int) or not 0 <= control <= 0x3f:
        raise ValueError('Palette control must be a 6-bit integer (0..0x3f)')
    if previous is None:
        result = [(0, 0, 0)] * TOTAL_COLORS
    else:
        if len(previous) != TOTAL_COLORS:
            raise ValueError('Previous palette must contain 3072 colors')
        result = list(previous)
    pointer = 0
    for page in range(PALETTE_PAGES):
        if control & (1 << page):
            if len(words) < pointer + PALETTE_PAGE_WORDS:
                raise ValueError(f'Not enough source RAM for enabled palette page {page}')
            offset = page * PALETTE_PAGE_WORDS
            result[offset:offset + PALETTE_PAGE_WORDS] = (
                [decode_palette_word(w) for w in words[pointer:pointer + PALETTE_PAGE_WORDS]]
            )
            pointer += PALETTE_PAGE_WORDS
        elif pointer:
            pointer += PALETTE_PAGE_WORDS
    return result


def color_group_base(layer: str, color: int) -> int:
    """Return palette index for pen 0 of a 16-pen color group."""
    if layer not in LAYER_PAGES:
        raise ValueError(f'Invalid palette page/layer: {layer}')
    if not isinstance(color, int) or not 0 <= color < 32:
        raise ValueError('CPS-1 color group must be 0..31')
    return LAYER_PAGES[layer] * PALETTE_PAGE_WORDS + color * COLOR_GROUP_SIZE


def gfxrom_bank_mapper(layer: str, code: int) -> int:
    """MAME CD63B mapper for dino; return -1 for unmapped tile codes.

    Two 0x8000 units cover 0..0xffff, shared by all four tile types.
    MAME converts incoming tile code to mapper units by shifting according
    to type, then returns the selected ROM tile code after reversing shift.
    """
    if layer not in MAPPER_SHIFTS:
        raise ValueError(f'Unsupported CD63B graphics layer: {layer}')
    if not isinstance(code, int):
        raise TypeError('Tile code must be an integer')
    if code < 0:
        return -1
    shift = MAPPER_SHIFTS[layer]
    addr = code << shift
    if not 0 <= addr <= 0xffff:
        return -1
    bank = addr // 0x8000
    base = bank * 0x8000
    return (base + (addr & 0x7fff)) >> shift


@dataclass(frozen=True)
class SpriteTile:
    """Relative on-screen tile in a CPS-1 composite sprite (16x16 cells)."""
    dx: int
    dy: int
    code: int
    flip_x: bool
    flip_y: bool


def sprite_block_tiles(code: int, attribute: int) -> list[SpriteTile]:
    """Expand CPS-1 blocked sprite metadata including hardware tile-code wrap.

    Does not do VRAM placement, clipping or per-pixel alpha composition.
    """
    if not isinstance(code, int) or not 0 <= code <= 0xffff:
        raise ValueError('Sprite tile code must be 16-bit')
    if not isinstance(attribute, int) or not 0 <= attribute <= 0xffff:
        raise ValueError('Sprite attribute must be 16-bit')
    nx = ((attribute >> 8) & 0xf) + 1 if (attribute & 0xff00) else 1
    ny = ((attribute >> 12) & 0xf) + 1 if (attribute & 0xff00) else 1
    flip_x, flip_y = bool(attribute & 0x20), bool(attribute & 0x40)
    cells = []
    for row in range(ny):
        for col in range(nx):
            xc = nx - 1 - col if flip_x else col
            yc = ny - 1 - row if flip_y else row
            mapped_code = (code & ~0xf) + ((code + xc) & 0xf) + 0x10 * yc
            cells.append(SpriteTile(col * 16, row * 16, mapped_code, flip_x, flip_y))
    return cells

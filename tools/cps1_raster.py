"""Reference-constrained CPS-1 scroll2 rowscroll and high-priority pens.

MAME cps1_v.cpp: cps1_update_transmasks, render_layers, screen_update_cps1.
"""

def scroll2_x_for_line(scrollx, screen_y, rowscroll, rowscroll_offset):
    """CPS-1 scroll2 scanline X. Caller passes screen raster y in 0..255.

    MAME: m_other[(i + otheroffs) & 0x3ff] and row (i+scrolly)&0x3ff.
    """
    if len(rowscroll) != 1024:
        raise ValueError('Rowscroll must contain 1024 16-bit values')
    if not 0 <= screen_y < 256:
        raise ValueError('Rowscroll raster y must be 0..255')
    if type(scrollx) is not int or type(rowscroll_offset) is not int:
        raise ValueError('Scroll registers must be integers')
    return scrollx + rowscroll[(screen_y + rowscroll_offset) & 0x3ff]


def pen_blocks_sprite(pen, group, priority_registers):
    """MAME set_transmask(group, priority[group]^0xffff, 0x8000).

    If the corresponding register bit is set, this background pen blocks
    subsequent CPS-1 sprite pixels drawn against the priority bitmap.
    Pen 15 is transparent (so never sets the block mask).
    """
    if len(priority_registers) != 4 or any(type(x) is not int or not 0 <= x <= 0xffff for x in priority_registers):
        raise ValueError('Expected four 16-bit priority-mask registers')
    if not isinstance(pen,int) or not 0 <= pen < 16:
        raise ValueError('Pen must be a 4-bit color index')
    if not isinstance(group,int) or not 0 <= group < 4:
        raise ValueError('Priority group must be 0..3')
    return pen != 15 and bool(priority_registers[group] & (1<<pen))

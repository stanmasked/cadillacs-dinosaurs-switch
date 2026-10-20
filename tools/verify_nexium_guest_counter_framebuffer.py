#!/usr/bin/env python3
"""Strict guest NRO submitted-framebuffer pixel witness (ROM-free Stage 248).

The real NRO must first consume Y/X/ZR in its rendered training room.
After normal arena_frame() draws the scene, guest code reads four exact
framebuffer pixel colors in distinct places: COUNTER! C glyph, enemy
impact cross, idle player body, ordinary lane background. The CSV is
written only after framebufferEnd() on the exact rendering iteration.

This samples the *native guest framebuffer*, not the emulator host
window, visible photons, physical Joy-Con latency or audible sound.
Synthetic test CSVs establish parser behavior but not real guest output.
"""
import argparse
import csv
import json
from pathlib import Path
import re

if __package__:
    from tools import verify_nexium_guest_live_counter_hid as live
else:
    import verify_nexium_guest_live_counter_hid as live

COLUMNS=(
    'event','render_iteration','arena_tick','feedback_ttl','impact_ttl',
    'caption_rgba','impact_rgba','player_rgba','background_rgba')
NUMERIC=COLUMNS[1:5]
COLORS=COLUMNS[5:]
HEX8=re.compile(r'[0-9A-F]{8}\Z')
# Two standard 32-bit RGBA8 byte-order interpretations are accepted,
# but all four independent pixel locations must use ONE consistent
# packing, never an arbitrary mix of colors from a forged row.
EXPECTED_PACKED={
    'ABGR':{
        'caption_rgba':'FFC9EB5B',
        'impact_rgba':'FFA4F3FF',
        'player_rgba':'FFD0B43E',
        'background_rgba':'FF4A533E',
    },
    'ARGB':{
        'caption_rgba':'FF5BEBC9',
        'impact_rgba':'FFFFF3A4',
        'player_rgba':'FF3EB4D0',
        'background_rgba':'FF3E534A',
    }
}
STATUS='GUEST_SUBMITTED_COUNTER_FRAMEBUFFER_PIXELS_WITNESSED'


def verify(path,live_csv):
    prior=live.verify(live_csv)
    if prior['status']!=live.STATUS:
        raise ValueError('no independent real rendered-arena input event')
    file=Path(path)
    if file.is_symlink() or not file.is_file():
        raise ValueError('missing genuine submitted-framebuffer guest CSV')
    if not 120<=file.stat().st_size<=512:
        raise ValueError('out of bounds submitted-framebuffer file')
    try:
        with file.open(encoding='ascii',newline='') as stream:
            reader=csv.DictReader(stream)
            if tuple(reader.fieldnames or ())!=COLUMNS:
                raise ValueError('wrong submitted-framebuffer schema')
            rows=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('invalid guest pixel record encoding') from exc
    if len(rows)!=1 or None in rows[0] or any(
            value is None for value in rows[0].values()):
        raise ValueError('expected exactly one complete submitted-frame row')
    row=rows[0]
    if row['event']!='SUBMITTED_COUNTER_FRAME':
        raise ValueError('not a counter framebuffer submit')
    parsed={}
    for key in NUMERIC:
        token=row[key]
        if (not token or not token.isascii() or not token.isdecimal()
                or (len(token)>1 and token.startswith('0'))
                or len(token)>10 or int(token)>0xffffffff):
            raise ValueError('noncanonical frame counter integer')
        parsed[key]=int(token)
    if (parsed['render_iteration']<=0 or
            parsed['arena_tick']<
            prior['counter_impact_relative_tick'] or
            not 1<=parsed['feedback_ttl']<=6 or
            not 1<=parsed['impact_ttl']<=6):
        raise ValueError('render frame outside guest counter visual window')
    for key in COLORS:
        if not HEX8.fullmatch(row[key]):
            raise ValueError('noncanonical framebuffer color')
    packing=next((
        name for name,expected in EXPECTED_PACKED.items()
        if all(row[key]==expected[key] for key in COLORS)
    ),None)
    if packing is None:
        raise ValueError('counter glyph, enemy impact, player or ground pixel incorrect')
    return {
        'schema':'dino-nexium-guest-counter-framebuffer-v1',
        'status':STATUS,
        'native_guest_framebuffer_pixels_verified':True,
        'framebuffer_end_called_before_report':True,
        'real_rendered_arena_zr_counter_required':True,
        'render_iteration':parsed['render_iteration'],
        'arena_tick':parsed['arena_tick'],
        'counter_caption_feedback_ttl':parsed['feedback_ttl'],
        'enemy_impact_flash_ttl':parsed['impact_ttl'],
        'rgba8_packing':packing,
        'independent_expected_counter_glyph_pixel':True,
        'independent_expected_enemy_impact_pixel':True,
        'independent_expected_player_and_background_pixels':True,
        'host_emulator_screen_pixel_verified':False,
        'physical_display_verified':False,
        'physical_joycon_verified':False,
        'audio_speaker_verified':False,
        'original_arcade_graphics_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--live-csv',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv)
    try:
        result=verify(a.report,a.live_csv)
    except (ValueError,OSError,UnicodeError,OverflowError):
        result={
            'schema':'dino-nexium-guest-counter-framebuffer-v1',
            'status':'INCONCLUSIVE_NO_VALID_GUEST_COUNTER_FRAMEBUFFER_PIXELS',
            'native_guest_framebuffer_pixels_verified':False,
            'host_emulator_screen_pixel_verified':False,
            'physical_display_verified':False,
        }
    a.out.write_text(json.dumps(result,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(result,sort_keys=True))
    # Experimental first pass is optional. Prior required Stage 247
    # game-state evidence MUST be checked separately and fail closed.
    return 0


if __name__=='__main__':
    raise SystemExit(main())

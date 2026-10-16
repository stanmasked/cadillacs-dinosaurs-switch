#!/usr/bin/env python3
"""Generate an opt-in CPS-1 dino VBlank OBJ latch patch for a local MAME checkout.

The tool does not distribute MAME code or copyrighted game data. It creates
a small unified diff against the user's own upstream MAME source checkout.
"""
import argparse
import difflib
from pathlib import Path
import sys

FUNCTION_ANCHOR = 'void cps_state::cps1_objram_latch(int state)'
COPY_ANCHOR = 'memcpy(m_buffered_obj.get(), m_obj, m_obj_size);'
MARKER = 'CPS1_OBJ_DUMP_DIR'

INSTRUMENT = r'''\n\t\t// Local opt-in research capture of the *latched* CPS-1 object buffer.
\t\t// Unlike gfx RAM, m_buffered_obj is what cps1_render_sprites reads.
\t\t// Restrict the hook to dino and a bounded frame-number window.
\t\tif (std::strcmp(machine().system().name, "dino") == 0)
\t\t{
\t\t\tconst char *directory = std::getenv("CPS1_OBJ_DUMP_DIR");
\t\t\tconst char *begin_text = std::getenv("CPS1_OBJ_DUMP_START");
\t\t\tconst char *count_text = std::getenv("CPS1_OBJ_DUMP_COUNT");
\t\t\tif (directory && *directory && begin_text && *begin_text && count_text && *count_text)
\t\t\t{
\t\t\t\tconst unsigned long long begin = std::strtoull(begin_text, nullptr, 10);
\t\t\t\tconst unsigned long long count = std::strtoull(count_text, nullptr, 10);
\t\t\t\tconst unsigned long long frame = m_screen->frame_number();
\t\t\t\tif (count > 0 && count <= 120 && frame >= begin && frame - begin < count)
\t\t\t\t{
\t\t\t\t\tchar filename[1024];
\t\t\t\t\tconst int size = std::snprintf(filename, sizeof(filename),
\t\t\t\t\t\t"%s/dino_obj_latch_frame-%08llu.be.bin", directory, frame);
\t\t\t\t\tif (size > 0 && static_cast<size_t>(size) < sizeof(filename))
\t\t\t\t\t{
\t\t\t\t\t\tif (std::FILE *file = std::fopen(filename, "wb"))
\t\t\t\t\t\t{
\t\t\t\t\t\t\tfor (int i = 0; i < m_obj_size / 2; ++i)
\t\t\t\t\t\t\t{
\t\t\t\t\t\t\t\tconst uint16_t word = m_buffered_obj[i];
\t\t\t\t\t\t\t\tconst unsigned char bytes[2] = {
\t\t\t\t\t\t\t\t\tstatic_cast<unsigned char>(word >> 8),
\t\t\t\t\t\t\t\t\tstatic_cast<unsigned char>(word & 0xff) };
\t\t\t\t\t\t\t\tif (std::fwrite(bytes, 1, sizeof(bytes), file) != sizeof(bytes))
\t\t\t\t\t\t\t\t\tbreak;  // disk failure: validator rejects incomplete file
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\tstd::fclose(file);
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
'''


def instrument(source: str) -> str:
    if MARKER in source:
        raise ValueError('CPS1 OBJ instrumentation is already present')
    pos = source.find(FUNCTION_ANCHOR)
    if pos == -1 or source.find(FUNCTION_ANCHOR, pos + 1) != -1:
        raise ValueError('Expected exactly one CPS-1 object-latch method')
    next_function = source.find('\n}', pos)
    if next_function == -1:
        raise ValueError('Could not locate end of object-latch method')
    body = source[pos:next_function]
    if body.count(COPY_ANCHOR) != 1:
        raise ValueError('Expected exactly one buffered-object memcpy in latch method')
    offset = pos + body.index(COPY_ANCHOR) + len(COPY_ANCHOR)
    result = source[:offset] + INSTRUMENT.replace(r'\n', '\n').replace(r'\t', '\t') + source[offset:]
    insertions = []
    for header in ('<cstdio>', '<cstdlib>', '<cstring>'):
        if f'#include {header}' not in result:
            insertions.append(f'#include {header}\n')
    if insertions:
        i = result.find('#include ')
        if i < 0:
            raise ValueError('MAME source has no #include anchor')
        result = result[:i] + ''.join(insertions) + result[i:]
    return result


def create_patch(source: str, source_path='src/mame/capcom/cps1_v.cpp') -> str:
    changed = instrument(source)
    patch = ''.join(difflib.unified_diff(
        source.splitlines(keepends=True), changed.splitlines(keepends=True),
        fromfile='a/' + source_path, tofile='b/' + source_path))
    if not patch or COPY_ANCHOR not in patch:
        raise AssertionError('No safe change generated')
    return patch


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mame_source', type=Path, help='Your own MAME src/mame/capcom/cps1_v.cpp')
    ap.add_argument('--patch', type=Path, required=True, help='New patch file, never overwrite')
    args = ap.parse_args(argv)
    try:
        patch = create_patch(args.mame_source.read_text(encoding='utf-8'))
        with args.patch.open('x', encoding='utf-8') as fp:
            fp.write(patch)
        print(f'Created local opt-in MAME OBJ patch: {args.patch}')
        return 0
    except (ValueError, OSError, AssertionError) as exc:
        print(f'Patch refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

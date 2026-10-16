#!/usr/bin/env python3
"""Generate opt-in MAME CPS-1 complete-render callback capture patch.

Captures RGB + latched OBJ + RAM/register/palette on the SAME screen_update
pass. Neither MAME source, ROMs nor extracted sprites are redistributed.
"""
import argparse
import difflib
from pathlib import Path
import sys

METHOD = 'uint32_t cps_state::screen_update_cps1(screen_device &screen, bitmap_ind16 &bitmap, const rectangle &cliprect)'
DRAW = 'render_layers(screen, bitmap, cliprect);'
MARKER = 'CPS1_RENDER_DUMP_DIR'

CODE = r'''
	// Experimental: copy screen RGB and its latched sprite inputs in one
	// complete CPS-1 rendering pass, NOT independently at VBlank/frame_done.
	if (std::strcmp(machine().system().name, "dino") == 0 &&
		cliprect.min_x <= 64 && cliprect.max_x >= 447 &&
		cliprect.min_y <= 16 && cliprect.max_y >= 239)
	{
		const char *dir = std::getenv("CPS1_RENDER_DUMP_DIR");
		const char *start_str = std::getenv("CPS1_RENDER_DUMP_START");
		const char *count_str = std::getenv("CPS1_RENDER_DUMP_COUNT");
		if (dir && *dir && start_str && *start_str && count_str && *count_str &&
			m_gfxram.bytes() >= 0x30000)
		{
			const unsigned long long first = std::strtoull(start_str, nullptr, 10);
			const unsigned long long count = std::strtoull(count_str, nullptr, 10);
			const unsigned long long frame = screen.frame_number();
			if (count >= 1 && count <= 120 && frame >= first && frame - first < count)
			{
				char stem[1024];
				const int n = std::snprintf(stem, sizeof(stem), "%s/frame-%08llu", dir, frame);
				if (n > 0 && static_cast<size_t>(n) + 40 < sizeof(stem))
				{
					auto dump_words = [&](const char *suffix, const uint16_t *words, size_t length) {
						char path[1024];
						std::snprintf(path, sizeof(path), "%s.%s", stem, suffix);
						if (std::FILE *f = std::fopen(path, "wb"))
						{
							for (size_t i = 0; i < length; ++i)
							{
								const uint16_t v = words[i];
								const unsigned char be[2] = {static_cast<unsigned char>(v >> 8),
									static_cast<unsigned char>(v & 255)};
								if (std::fwrite(be, 1, 2, f) != 2) break;
							}
							std::fclose(f);
						}
					};
					auto open_suffix = [&](const char *suffix) -> std::FILE * {
						char path[1024];
						std::snprintf(path, sizeof(path), "%s.%s", stem, suffix);
						return std::fopen(path, "wb");
					};
					dump_words("gfxram-be.bin", &m_gfxram[0], 0x30000 / 2);
					dump_words("cps-a-be.bin", &m_cps_a_regs[0], 0x40 / 2);
					dump_words("cps-b-be.bin", &m_cps_b_regs[0], 0x40 / 2);
					dump_words("buffered-obj-be.bin", m_buffered_obj.get(), m_obj_size / 2);
					if (std::FILE *f = open_suffix("palette-rgb24.bin"))
					{
						for (unsigned i = 0; i < 0xc00; ++i)
						{
							const rgb_t c = m_palette->pen_color(i);
							const unsigned char rgb[3] = {c.r(), c.g(), c.b()};
							if (std::fwrite(rgb, 1, 3, f) != 3) break;
						}
						std::fclose(f);
					}
					if (std::FILE *f = open_suffix("reference-rgb24.bin"))
					{
						for (int y = 16; y <= 239; ++y)
						for (int x = 64; x <= 447; ++x)
						{
							const rgb_t c = m_palette->pen_color(bitmap.pix(y, x));
							const unsigned char rgb[3] = {c.r(), c.g(), c.b()};
							if (std::fwrite(rgb, 1, 3, f) != 3) break;
						}
						std::fclose(f);
					}
					if (std::FILE *f = open_suffix("manifest.json"))
					{
						std::fprintf(f, "{\"game\":\"dino\",\"frame\":%llu,"
								"\"capture_hook\":\"screen_update_cps1_complete\","
								"\"full_cliprect\":true,\"buffered_obj_same_render_pass\":true,"
								"\"reference_width\":384,\"reference_height\":224,"
								"\"reference_pixel_encoding\":\"rgb24_palette_resolved\","
								"\"raw_word_endianness\":\"big\","
								"\"palette_source\":\"MAME_effective_pen_color\","
								"\"gfxram_bytes\":196608,\"cps_a_bytes\":64,\"cps_b_bytes\":64,"
								"\"buffered_obj_bytes\":2048,\"palette_bytes\":9216,"
								"\"reference_rgb_bytes\":258048,"
								"\"pixel_parity_verified\":false}\n", frame);
						std::fclose(f);
					}
				}
			}
		}
	}
'''


def instrument(source):
    if MARKER in source:
        raise ValueError('Render capture already inserted')
    start = source.find(METHOD)
    if start < 0 or source.find(METHOD, start + len(METHOD)) >= 0:
        raise ValueError('Expected exactly one screen_update_cps1 definition')
    end = source.find('\n}', start)
    if end < 0:
        raise ValueError('Cannot locate screen_update_cps1 end')
    fragment = source[start:end]
    if fragment.count(DRAW) != 1:
        raise ValueError('Unexpected render_layers call count')
    offset = start + fragment.index(DRAW) + len(DRAW)
    updated = source[:offset] + CODE + source[offset:]
    includes = ''.join(f'#include {header}\n'
                       for header in ('<cstdio>', '<cstdlib>', '<cstring>')
                       if f'#include {header}' not in updated)
    if includes:
        pos = updated.find('#include ')
        if pos < 0:
            raise ValueError('Missing MAME #include location')
        updated = updated[:pos] + includes + updated[pos:]
    return updated


def create_patch(source, path='src/mame/capcom/cps1_v.cpp'):
    updated = instrument(source)
    return ''.join(difflib.unified_diff(
        source.splitlines(keepends=True), updated.splitlines(keepends=True),
        fromfile='a/' + path, tofile='b/' + path))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--patch', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        patch = create_patch(args.source.read_text(encoding='utf8'))
        with args.patch.open('x', encoding='utf8') as out:
            out.write(patch)
        print('Local MAME render-pass capture patch:', args.patch)
        return 0
    except (ValueError, OSError) as exc:
        print('Patch generation refused:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

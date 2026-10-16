#!/usr/bin/env python3
"""Create an opt-in private MAME 0.289 source copy with a dino OBJ probe.

This does NOT compile MAME, modify its source in place, or contain ROM data.
MAME's internal VBlank-latched m_buffered_obj cannot be obtained from the
ordinary QSound gfx RAM Lua share. Probe output is diagnostic-only until
frame-number, capture timing and exact pixel alignment are independently
verified on a running MAME 0.289 build.
"""
import argparse
import hashlib
from pathlib import Path
import sys

# Git blob of upstream mamedev/mame tag mame0289, src/mame/capcom/cps1_v.cpp.
EXPECTED_MAME_BLOB = 'c1b5e3867824d0d1877b981142db7741346d2c55'
INCLUDE = '#include "cps1.h"\n'
HOOK = '\tfind_last_sprite();\n\n\tcps1_update_transmasks();'
PROBE_MARKER = 'CPS1_DINO_OBJ_PROBE_V1'

# This block runs *during the MAME video update*, after find_last_sprite()
# and before render_layers() consumes m_buffered_obj. It writes the exact
# buffered 0x400 words in big-endian order, not live/unlatched gfx RAM.
# Scope strictly to dino and the same six frame numbers as the Lua script.
PROBE = r'''
	// CPS1_DINO_OBJ_PROBE_V1: private local diagnostic only.
	// Verify frame_done/renderer counter agreement before claiming parity.
	if (std::strcmp(machine().system().name, "dino") == 0 &&
			m_obj_size == 0x800 && m_buffered_obj)
	{
		const unsigned long long frame_number =
				static_cast<unsigned long long>(screen.frame_number());
		if (frame_number >= 900 && frame_number <= 910 &&
				((frame_number - 900) % 2) == 0)
		{
			char path[128];
			std::snprintf(path, sizeof(path),
				"cps1-captures/frame-%08llu.buffered-obj-be.bin", frame_number);
			std::FILE *existing = std::fopen(path, "rb");
			if (existing)
			{
				std::fclose(existing);
			}
			else
			{
				std::FILE *output = std::fopen(path, "wb");
				if (!output)
					osd_printf_warning("OBJ probe: unable to open %s\\n", path);
				else
				{
					bool complete = true;
					for (unsigned index = 0; index < 0x400; ++index)
					{
						const unsigned word = m_buffered_obj[index];
						if (std::fputc((word >> 8) & 255, output) == EOF ||
								std::fputc(word & 255, output) == EOF)
						{
							complete = false;
							break;
						}
					}
					if (std::fclose(output) != 0)
						complete = false;
					if (!complete)
						osd_printf_warning("OBJ probe: incomplete %s\\n", path);
				}
			}
		}
	}
'''


def git_blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') +
                        b'\0' + data).hexdigest()


def instrument(source):
    """Inject only where the verified upstream video-update anchor exists."""
    if not isinstance(source, str) or PROBE_MARKER in source:
        raise ValueError('Invalid or already instrumented CPS-1 source')
    if source.count(INCLUDE) != 1 or source.count(HOOK) != 1:
        raise ValueError('MAME 0.289 CPS-1 probe anchors are missing or ambiguous')
    if 'void cps_state::cps1_objram_latch(int state)' not in source:
        raise ValueError('CPS-1 VBlank-latched OBJ implementation not found')
    result = source.replace(INCLUDE,
                            INCLUDE + '#include <cstdio>\n#include <cstring>\n', 1)
    return result.replace(HOOK,
                          '\tfind_last_sprite();\n' + PROBE +
                          '\n\tcps1_update_transmasks();', 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mame_cps1_video_cpp', type=Path,
                        help='Unmodified MAME 0.289 src/mame/capcom/cps1_v.cpp')
    parser.add_argument('--out', type=Path, required=True,
                        help='New instrumented local .cpp copy; never overwrites')
    args = parser.parse_args(argv)
    try:
        source_file = args.mame_cps1_video_cpp.resolve()
        destination = args.out.resolve()
        if source_file == destination:
            raise ValueError('Cannot overwrite the original MAME source')
        raw = source_file.read_bytes()
        if git_blob_sha(raw) != EXPECTED_MAME_BLOB:
            raise ValueError('Expected unmodified mamedev/mame 0.289 cps1_v.cpp')
        modified = instrument(raw.decode('utf-8')).encode('utf-8')
        with destination.open('xb') as file:
            file.write(modified)
        print('Created opt-in MAME 0.289 OBJ probe source:', destination)
        print('Original source remains unchanged. No MAME build performed.')
        print('Output is diagnostic-only; frame counter/timing need confirmation.')
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print(f'OBJ probe refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

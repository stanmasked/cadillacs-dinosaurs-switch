#!/usr/bin/env python3
"""Stage290: apply bounded source-anchored trace hooks to Stage286 MAME 0.106.

Apply ONLY after the checked-in Stage286 MNG-window patch to the exact pinned
mamedev/historic-mame mame0106 source. No game assets or recording data.
"""
import argparse
from pathlib import Path


def _replace_once(text, old, new, path):
    if text.count(old) != 1:
        raise ValueError(f"{path}: expected exactly one anchored source snippet")
    return text.replace(old, new, 1)


def instrument(root):
    root = Path(root)
    replacements = {
        "src/inptport.c": [
            ('#include "driver.h"\n',
             '#include "driver.h"\n#include "video.h"\n'),
            (
                '\t\tif (mame_fread(Machine->playback_file, &result, sizeof(result)) == sizeof(result))\n'
                '\t\t\tportvalue = port_info[portnum].playback = BIG_ENDIANIZE_INT32(result);',
                '\t\tif (mame_fread(Machine->playback_file, &result, sizeof(result)) == sizeof(result))\n'
                '\t\t{\n'
                '\t\t\tstage290_note_playback_word(portnum);\n'
                '\t\t\tportvalue = port_info[portnum].playback = BIG_ENDIANIZE_INT32(result);\n'
                '\t\t}',
            ),
        ],
        "src/video.h": [
            ('extern int mng_capture_frame_count;\n',
             'extern int mng_capture_frame_count;\n'
             'extern int mng_count_trace;\n'
             'void stage290_note_playback_word(int portnum);\n'),
        ],
        "src/windows/video.h": [
            ('extern int mng_capture_frame_count;\n',
             'extern int mng_capture_frame_count;\n'
             'extern int mng_count_trace;\n'),
        ],
        "src/windows/video.c": [
            (
                '\t{ "mngframes", NULL, rc_int, &mng_capture_frame_count, "0", 0, 3601, NULL, "number of MNG frames to capture (0 means unlimited)" },\n',
                '\t{ "mngframes", NULL, rc_int, &mng_capture_frame_count, "0", 0, 3601, NULL, "number of MNG frames to capture (0 means unlimited)" },\n'
                '\t{ "mngcounttrace", NULL, rc_bool, &mng_count_trace, "0", 0, 0, NULL, "privately log input read and movie callback counters" },\n',
            ),
        ],
        "src/video.c": [
            ('#include "png.h"\n',
             '#include "png.h"\n#include <stdio.h>\n'),
            (
                'int mng_capture_frame_count = 0;\n',
                'int mng_capture_frame_count = 0;\n'
                'int mng_count_trace = 0;\n'
                'static unsigned int stage290_first_port_reads = 0;\n'
                'static unsigned int stage290_playback_words = 0;\n'
                'static FILE *stage290_trace_file = NULL;\n'
                '\n'
                'void stage290_note_playback_word(int portnum)\n'
                '{\n'
                '\tif (mng_count_trace)\n'
                '\t{\n'
                '\t\tstage290_playback_words++;\n'
                '\t\tif (portnum == 0)\n'
                '\t\t\tstage290_first_port_reads++;\n'
                '\t}\n'
                '}\n',
            ),
            (
                '\tmovie_frame = 0;\n'
                '\tmovie_frames_written = 0;\n'
                '}\n'
                '\n'
                '\n'
                'void record_movie_stop(void)',
                '\tmovie_frame = 0;\n'
                '\tmovie_frames_written = 0;\n'
                '\tif (stage290_trace_file != NULL)\n'
                '\t{\n'
                '\t\tfclose(stage290_trace_file);\n'
                '\t\tstage290_trace_file = NULL;\n'
                '\t}\n'
                '\tif (mng_count_trace && movie_file != NULL)\n'
                '\t{\n'
                '\t\tstage290_trace_file = fopen("stage290-mng-counts.csv", "wb");\n'
                '\t\tif (stage290_trace_file != NULL)\n'
                '\t\t\tfputs("callback_index,first_port_reads,playback_words\\n", stage290_trace_file);\n'
                '\t}\n'
                '}\n'
                '\n'
                '\n'
                'void record_movie_stop(void)',
            ),
            (
                '\t\tmovie_file = NULL;\n'
                '\t}\n'
                '}\n'
                '\n'
                '\n'
                'void record_movie_toggle(void)',
                '\t\tmovie_file = NULL;\n'
                '\t}\n'
                '\tif (stage290_trace_file != NULL)\n'
                '\t{\n'
                '\t\tfclose(stage290_trace_file);\n'
                '\t\tstage290_trace_file = NULL;\n'
                '\t}\n'
                '}\n'
                '\n'
                '\n'
                'void record_movie_toggle(void)',
            ),
            (
                '\t\tsave_frame_with(movie_file, bitmap, mng_capture_frame);\n'
                '\n'
                '\t\tif (mng_capture_frame_count > 0 &&',
                '\t\tsave_frame_with(movie_file, bitmap, mng_capture_frame);\n'
                '\t\tif (stage290_trace_file != NULL)\n'
                '\t\t\tfprintf(stage290_trace_file, "%d,%u,%u\\n",\n'
                '\t\t\t\tcurrent_frame, stage290_first_port_reads, stage290_playback_words);\n'
                '\n'
                '\t\tif (mng_capture_frame_count > 0 &&',
            ),
        ],
    }
    changed = []
    # Two-phase process: no writes unless every anchored replacement succeeds.
    pending = []
    for relative, operations in replacements.items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"source file missing or symlinked: {relative}")
        original = path.read_bytes()
        if b"\r\n" in original:
            raise ValueError(f"normalize LF before Stage290 instrumentation: {relative}")
        body = original.decode("utf-8")
        for old, new in operations:
            body = _replace_once(body, old, new, relative)
        pending.append((path, body.encode("utf-8")))
        changed.append(relative)
    for path, data in pending:
        path.write_bytes(data)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    for item in instrument(args.root):
        print("instrumented:", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

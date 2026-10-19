"""Compile the portable fixed-size guest ACK buffer as native C.

No ROM or real audio. The mock drives known observations then independently
parses the delayed CSV through the actual production guest-trace verifier.
"""
import csv
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import verify_nexium_audio_ack_tick_trace as check

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include "dino_guest_ack_trace.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static DinoGuestAckTrace trace;
static const char *header=
    "tick,frame_id,batch_size,batch_position,released,mid_released,"
    "mid_calls,submitted,skipped,pre_poll_full,pre_poll_recovered,"
    "pending,audio_errors\n";

int main(int argc, char **argv) {
    if (argc != 2) return 10;
    dino_guest_ack_trace_reset(&trace);
    if (dino_guest_ack_trace_write_csv(stdout,&trace)) return 11;
    if (dino_guest_ack_trace_append(NULL,NULL)) return 12;
    for (uint32_t tick=0;tick<900u;++tick) {
        uint32_t line[13]={tick+1u,tick+1u,1u,0u,1u,0u,0u,
                            1u,0u,0u,0u,1u,0u};
        if (!dino_guest_ack_trace_append(&trace,line)) return 13;
    }
    if (trace.used!=900u || trace.overflow) return 14;
    uint32_t last[13]={0};
    if (dino_guest_ack_trace_append(&trace,last) || !trace.overflow)
        return 15;
    FILE *bad=fopen(argv[1],"w");
    if (!bad) return 16;
    if (dino_guest_ack_trace_write_csv(bad,&trace)) return 17;
    if (fclose(bad)!=0) return 18;
    dino_guest_ack_trace_reset(&trace);
    for (uint32_t tick=0;tick<900u;++tick) {
        uint32_t line[13]={tick+1u,tick+1u,1u,0u,1u,0u,0u,
                            1u,0u,0u,0u,1u,0u};
        if (!dino_guest_ack_trace_append(&trace,line)) return 19;
    }
    if (trace.used!=900u || trace.overflow) return 20;
    FILE *f=fopen(argv[1],"w");
    if (!f) return 21;
    if (!dino_guest_ack_trace_write_csv(f,&trace)) return 22;
    if (fclose(f)!=0) return 23;
    return 0;
}
'''


class BufferedGuestACKTraceTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('gcc'), 'Native GCC needed')
    def test_900_guest_ticks_buffered_and_emitted_only_when_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            harness=base/'harness.c'
            harness.write_text(HARNESS,encoding='ascii')
            exe=base/'runner'
            cmd=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                 '-Isource',str(harness),'source/dino_guest_ack_trace.c',
                 '-o',str(exe)]
            compile=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(compile.returncode,0,compile.stderr)
            out=base/'trace.csv'
            run=subprocess.run([str(exe),str(out)],cwd=ROOT,
                               capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            raw,rows=check.parse_csv(out)
            self.assertEqual(len(rows),900)
            self.assertTrue(raw.endswith(b'900,900,1,0,1,0,0,1,0,0,0,1,0\n'))
            for tick,row in enumerate(rows,1):
                self.assertEqual(row['tick'],tick)
                self.assertEqual(row['frame_id'],tick)
                self.assertEqual(row['pending'],1)
                self.assertEqual(row['released'],1)
                self.assertEqual(row['audio_errors'],0)

    def test_loop_has_no_per_tick_csv_filesystem_or_libnx_poll(self):
        main=(ROOT/'source/main.c').read_text(encoding='utf-8')
        step=main.split('if (guest_ack_tick_collecting) {',1)[1].split(
            'if (arena_ticks>=2u) {',1)[0]
        self.assertIn('dino_guest_ack_trace_append(',step)
        self.assertNotIn('fprintf(',step)
        self.assertNotIn('fopen(',step)
        self.assertNotIn('fflush(',step)
        self.assertNotIn('audoutGetReleasedAudioOutBuffer',step)
        self.assertIn('dino_guest_ack_trace_write_csv(',main)
        self.assertIn('const int closed=fclose(ack_output);',main)
        self.assertIn('if (!complete || closed!=0)',main)
        self.assertIn('#ifdef DINO_EMULATOR_SELFTEST\n#include "dino_guest_ack_trace.h"',
                      main)
        self.assertNotIn('FILE *guest_ack_tick_trace=NULL;',main)
        self.assertEqual(main.count('dino_guest_ack_trace_write_csv('),1)

    def test_buffer_is_900_by_13_and_contains_no_private_assets(self):
        header=(ROOT/'source/dino_guest_ack_trace.h').read_text(encoding='ascii')
        implementation=(ROOT/'source/dino_guest_ack_trace.c').read_text(
            encoding='ascii')
        self.assertIn('DINO_GUEST_ACK_TRACE_TICKS=900',header)
        self.assertIn('DINO_GUEST_ACK_TRACE_COLUMNS=13',header)
        self.assertIn('trace->used!=DINO_GUEST_ACK_TRACE_TICKS',implementation)
        self.assertIn('trace->used>=DINO_GUEST_ACK_TRACE_TICKS',implementation)
        self.assertIn('memcpy(trace->rows[trace->used],fields,',implementation)
        for forbidden in ('sdmc:/','dino.zip','gfx.bin',
                          'audoutGetReleasedAudioOutBuffer'):
            self.assertNotIn(forbidden,implementation)


if __name__=="__main__":
    unittest.main()

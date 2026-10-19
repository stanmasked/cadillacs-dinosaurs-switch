#include "dino_guest_frame_clock.h"

/* All per-frame capture is fixed-size RAM arithmetic; no I/O here. */
void dino_guest_frame_clock_reset(DinoGuestFrameClock *trace) {
    if (!trace) return;
    trace->used=0;
    trace->stress_ticks=0;
    trace->overflow=false;
}

bool dino_guest_frame_clock_append(
    DinoGuestFrameClock *trace,DinoGuestFrameClockRow row) {
    if (!trace || trace->overflow) return false;
    if (trace->used>=DINO_GUEST_FRAME_CLOCK_MAX_ROWS ||
        row.frame_id==0 || row.elapsed_ns_capped>250000000u ||
        row.frame_game_ticks>15u ||
        row.stress_game_ticks>row.frame_game_ticks ||
        row.stress_game_ticks>
            DINO_GUEST_FRAME_CLOCK_GAME_TICKS-trace->stress_ticks ||
        (trace->used && row.frame_id!=trace->rows[trace->used-1].frame_id+1u)) {
        trace->overflow=true;
        return false;
    }
    trace->rows[trace->used++]=row;
    trace->stress_ticks+=row.stress_game_ticks;
    return true;
}

/* Serialize once, strictly AFTER the final measured game tick. Partial,
 * overflowed or missing frame evidence must never become a valid report.
 * These are already CLAMPED scheduler intervals, not hardware timestamps. */
bool dino_guest_frame_clock_write_csv(FILE *file,
                                      const DinoGuestFrameClock *trace) {
    if (!file || !trace || trace->overflow || trace->used==0 ||
        trace->stress_ticks!=DINO_GUEST_FRAME_CLOCK_GAME_TICKS)
        return false;
    if (fputs(
        "frame_id,elapsed_ns_capped,frame_game_ticks,stress_game_ticks\n",
        file)==EOF)
        return false;
    for (uint32_t i=0;i<trace->used;++i) {
        const DinoGuestFrameClockRow *r=&trace->rows[i];
        if (fprintf(file,"%u,%u,%u,%u\n",
                    (unsigned)r->frame_id,
                    (unsigned)r->elapsed_ns_capped,
                    (unsigned)r->frame_game_ticks,
                    (unsigned)r->stress_game_ticks)<0)
            return false;
    }
    return fflush(file)==0;
}

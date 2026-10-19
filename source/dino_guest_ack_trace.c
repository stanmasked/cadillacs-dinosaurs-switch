#include "dino_guest_ack_trace.h"
#include <string.h>

/* Portable ROM-free bounded storage. No system calls, file handles or
 * audio-service polling in the one-call-per-game-tick append path. */
void dino_guest_ack_trace_reset(DinoGuestAckTrace *trace) {
    if (!trace) return;
    trace->used=0;
    trace->overflow=false;
}

bool dino_guest_ack_trace_append(
    DinoGuestAckTrace *trace,
    const uint32_t fields[DINO_GUEST_ACK_TRACE_COLUMNS]) {
    if (!trace || !fields) return false;
    if (trace->overflow || trace->used>=DINO_GUEST_ACK_TRACE_TICKS) {
        trace->overflow=true;
        return false;
    }
    memcpy(trace->rows[trace->used],fields,
           DINO_GUEST_ACK_TRACE_COLUMNS*sizeof(uint32_t));
    ++trace->used;
    return true;
}

/* Only invoke after 900 ticks: fail closed on truncated/overflowed traces.
 * No PCM payload, SD paths, secrets or audio-service timing are stored. */
bool dino_guest_ack_trace_write_csv(FILE *file,
                                    const DinoGuestAckTrace *trace) {
    if (!file || !trace || trace->overflow ||
        trace->used!=DINO_GUEST_ACK_TRACE_TICKS)
        return false;
    if (fputs(
        "tick,frame_id,batch_size,batch_position,released,mid_released,"
        "mid_calls,submitted,skipped,pre_poll_full,pre_poll_recovered,"
        "pending,audio_errors\n",file)==EOF)
        return false;
    for (unsigned i=0;i<DINO_GUEST_ACK_TRACE_TICKS;++i) {
        const uint32_t *r=trace->rows[i];
        if (fprintf(file,
            "%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
            (unsigned)r[0],(unsigned)r[1],(unsigned)r[2],
            (unsigned)r[3],(unsigned)r[4],(unsigned)r[5],
            (unsigned)r[6],(unsigned)r[7],(unsigned)r[8],
            (unsigned)r[9],(unsigned)r[10],(unsigned)r[11],
            (unsigned)r[12])<0)
            return false;
    }
    return fflush(file)==0;
}

#ifndef DINO_GUEST_ACK_TRACE_INCLUDED_H
#define DINO_GUEST_ACK_TRACE_INCLUDED_H
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

/* ROM-free guest selftest evidence only. Caller must not call CSV output
 * until AFTER its fixed-duration 900-tick measurement is complete.
 * Time is a simulation tick, never audout service/speaker wall-clock. */
enum { DINO_GUEST_ACK_TRACE_TICKS=900, DINO_GUEST_ACK_TRACE_COLUMNS=13 };
typedef struct {
    uint32_t rows[DINO_GUEST_ACK_TRACE_TICKS][DINO_GUEST_ACK_TRACE_COLUMNS];
    uint32_t used;
    bool overflow;
} DinoGuestAckTrace;
void dino_guest_ack_trace_reset(DinoGuestAckTrace *trace);
bool dino_guest_ack_trace_append(
    DinoGuestAckTrace *trace,
    const uint32_t fields[DINO_GUEST_ACK_TRACE_COLUMNS]);
bool dino_guest_ack_trace_write_csv(FILE *file,const DinoGuestAckTrace *trace);
#endif

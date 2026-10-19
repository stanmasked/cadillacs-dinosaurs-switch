#ifndef DINO_GUEST_FRAME_CLOCK_INCLUDED_H
#define DINO_GUEST_FRAME_CLOCK_INCLUDED_H

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

/* ROM-free selftest only. Read from the EXISTING frame scheduler clock;
 * append is RAM-only and must never call libnx, sleep or access SD. */
enum {
    DINO_GUEST_FRAME_CLOCK_MAX_ROWS=4096,
    DINO_GUEST_FRAME_CLOCK_GAME_TICKS=900
};
typedef struct {
    uint32_t frame_id;
    uint32_t elapsed_ns_capped;
    uint32_t frame_game_ticks;
    uint32_t stress_game_ticks;
} DinoGuestFrameClockRow;
typedef struct {
    DinoGuestFrameClockRow rows[DINO_GUEST_FRAME_CLOCK_MAX_ROWS];
    uint32_t used;
    uint32_t stress_ticks;
    bool overflow;
} DinoGuestFrameClock;

void dino_guest_frame_clock_reset(DinoGuestFrameClock *trace);
bool dino_guest_frame_clock_append(
    DinoGuestFrameClock *trace,DinoGuestFrameClockRow row);
bool dino_guest_frame_clock_write_csv(FILE *file,
                                      const DinoGuestFrameClock *trace);
#endif

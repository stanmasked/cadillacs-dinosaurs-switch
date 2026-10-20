/* Stage 269. Deterministic headless ROM-FREE training arena observations.
 * Portable C diagnostic only, NOT CPS-1 emulator or Capcom game mechanics.
 * Print deliberately explicit numeric fields, never C struct padding.
 */
#include "dino_arena.h"
#include <stdint.h>
#include <stdio.h>

static DinoArena arena;
static uint8_t caption_ttl;

static int step(const char *scene, unsigned i, unsigned held, unsigned edge) {
    dino_arena_step(&arena, held, edge);
    caption_ttl = dino_arena_counter_feedback_tick(caption_ttl, arena.events);
    if (arena.x < 16 || arena.x > 368 ||
        arena.y < 80 || arena.y > 208 ||
        arena.dummy_x < 16 || arena.dummy_x > 368 ||
        arena.dummy_y < 80 || arena.dummy_y > 208 ||
        arena.z < 0 || arena.player_hp > 5 || arena.dummy_hp > 3 ||
        arena.combo_hits > 3 || caption_ttl > 6)
        return 0;
    return printf("%s,%u,%u,%d,%d,%d,%u,%u,%d,%u,%u,%u,%u\n",
                  scene, i, (unsigned)arena.ticks,
                  (int)arena.x, (int)arena.y, (int)arena.z,
                  (unsigned)arena.player_hp, (unsigned)arena.dummy_hp,
                  (int)arena.dummy_x, (unsigned)arena.dummy_windup,
                  (unsigned)arena.combo_hits, (unsigned)arena.events,
                  (unsigned)caption_ttl) > 0;
}

static int target(void) {
    unsigned hits = 0, finishers = 0, knockouts = 0;
    dino_arena_reset(&arena);
    caption_ttl = 0;
    for (unsigned i = 0; i < 120; ++i) {
        unsigned held = i < 70 ? DINO_ARENA_RIGHT : 0;
        unsigned edge = (i == 75 || i == 90 || i == 105)
                        ? DINO_ARENA_ATTACK : 0;
        if (!step("target", i, held, edge)) return 0;
        hits += !!(arena.events & DINO_EVT_DUMMY_HIT);
        finishers += !!(arena.events & DINO_EVT_FINISHER);
        knockouts += !!(arena.events & DINO_EVT_DUMMY_KO);
    }
    return hits == 3 && finishers == 1 && knockouts == 1 &&
           arena.successful_hits == 3 && arena.dummy_hp == 0 &&
           arena.x == 230;
}

static int counter(void) {
    unsigned counters = 0;
    dino_arena_reset(&arena);
    caption_ttl = 0;
    for (unsigned i = 0; i < 140; ++i) {
        unsigned edge = i == 0 ? DINO_ARENA_TOGGLE_SPAR :
                        i == 116 ? DINO_ARENA_COUNTER : 0;
        if (!step("counter", i, 0, edge)) return 0;
        counters += !!(arena.events & DINO_EVT_COUNTER);
        if (i == 116 && (!(arena.events & DINO_EVT_COUNTER) ||
                         arena.dummy_cooldown != 48 ||
                         arena.dummy_hitstun != 9 || caption_ttl != 6))
            return 0;
    }
    return counters == 1 && arena.dummy_hp == 3;
}

static int dodge(void) {
    unsigned dodges = 0;
    dino_arena_reset(&arena);
    arena.x = 220; /* documented staged depth-lane setup */
    caption_ttl = 0;
    for (unsigned i = 0; i < 22; ++i) {
        unsigned edge = i == 0 ? DINO_ARENA_TOGGLE_SPAR :
                        i == 1 ? DINO_ARENA_JUMP : 0;
        if (!step("dodge", i, 0, edge)) return 0;
        dodges += !!(arena.events & DINO_EVT_DODGE);
    }
    return dodges == 1 && arena.player_hp == 5 &&
           arena.player_hits_taken == 0;
}

static int player_ko(void) {
    unsigned knockouts = 0;
    dino_arena_reset(&arena);
    arena.x = 220; /* explicit single-hit KO test setup */
    caption_ttl = 0;
    for (unsigned i = 0; i < 5; ++i) {
        if (i == 1) {
            arena.player_hp = 1;
            arena.dummy_windup = 1;
            arena.player_invuln = 0;
        }
        if (!step("player_ko", i, 0,
                  i == 0 ? DINO_ARENA_TOGGLE_SPAR : 0)) return 0;
        knockouts += !!(arena.events & DINO_EVT_PLAYER_KO);
    }
    return knockouts == 1 && arena.player_hp == 0 &&
           arena.player_hits_taken == 1;
}

int main(void) {
    if (puts("scene,step,tick,x,y,z,player_hp,dummy_hp,dummy_x,"
             "dummy_windup,combo_hits,events,counter_feedback_ttl") < 0)
        return 2;
    if (!target() || !counter() || !dodge() || !player_ko())
        return 3;
    return fflush(stdout) == 0 ? 0 : 4;
}

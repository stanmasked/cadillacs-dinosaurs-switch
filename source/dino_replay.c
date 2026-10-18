#include "dino_replay.h"
#include "dino_arena.h"

/* Single input timeline for platform-portable gameplay QA.
 * 70 ticks walking toward the opponent, three practice blows,
 * sparring mode start, fourth strike, then a jump to try a dodge.
 */
bool dino_replay_input(uint32_t tick,uint32_t *held,uint32_t *pressed) {
    if (!held || !pressed || tick>=DINO_REPLAY_TICKS) return false;
    uint32_t h=tick<70u ? DINO_ARENA_RIGHT : 0u;
    uint32_t p=(tick==75u || tick==90u || tick==105u || tick==148u)
                 ? DINO_ARENA_ATTACK : 0u;
    if (tick==130u) p|=DINO_ARENA_TOGGLE_SPAR;
    if (tick==155u) p|=DINO_ARENA_JUMP;
    *held=h;
    *pressed=p;
    return true;
}

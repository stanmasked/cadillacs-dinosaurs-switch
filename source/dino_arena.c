#include "dino_arena.h"
#include <stddef.h>

/* Fixed 60 Hz, integer-only, intentionally invented training rules.
 * This advances a MOVABLE PLACEHOLDER vs a STATIC TRAINING DUMMY;
 * original CPS-1 AI, hitboxes, animation and content are not emulated.
 */
static int32_t clamp(int32_t value, int32_t low, int32_t high) {
    if (value < low) return low;
    if (value > high) return high;
    return value;
}

void dino_arena_reset(DinoArena *arena) {
    if (!arena) return;
    *arena=(DinoArena){
        .x=90, .y=151, .z=0, .vz=0,
        .dummy_x=250, .dummy_y=151,
        .facing_right=1, .dummy_hp=3
    };
}

void dino_arena_step(DinoArena *arena, uint32_t held, uint32_t pressed) {
    if (!arena) return;
    /* All button input is untrusted; ignore unknown bits. */
    held &= (DINO_ARENA_LEFT|DINO_ARENA_RIGHT|
             DINO_ARENA_UP|DINO_ARENA_DOWN);
    pressed &= (DINO_ARENA_ATTACK|DINO_ARENA_JUMP);
    if (arena->dummy_hitstun) --arena->dummy_hitstun;
    if (arena->attack_frames) --arena->attack_frames;
    if (arena->attack_cooldown) --arena->attack_cooldown;

    int dx=((held&DINO_ARENA_RIGHT)!=0)-((held&DINO_ARENA_LEFT)!=0);
    int dy=((held&DINO_ARENA_DOWN)!=0)-((held&DINO_ARENA_UP)!=0);
    arena->x=clamp(arena->x+2*dx,16,DINO_ARENA_WIDTH-16);
    arena->y=clamp(arena->y+dy,80,DINO_ARENA_HEIGHT-16);
    if (dx) arena->facing_right=(uint8_t)(dx>0);

    if ((pressed&DINO_ARENA_JUMP) && arena->z==0 && arena->vz==0)
        arena->vz=8;
    if (arena->z>0 || arena->vz>0) {
        arena->z+=arena->vz;
        --arena->vz;
        if (arena->z<=0) { arena->z=0;arena->vz=0; }
    }

    if ((pressed&DINO_ARENA_ATTACK) && !arena->attack_cooldown) {
        arena->attack_frames=8;
        arena->attack_cooldown=15;
        int delta=arena->dummy_x-arena->x;
        int lane=arena->dummy_y-arena->y;
        if (lane<0) lane=-lane;
        int in_front=arena->facing_right ? delta>=0 : delta<=0;
        int distance=delta<0 ? -delta : delta;
        /* Attack only in front, within range, in the same depth lane,
         * and before the jumping actor becomes too high to reach. */
        if (arena->dummy_hp>0 && in_front && distance<=38 &&
            lane<=15 && arena->z<=20) {
            --arena->dummy_hp;
            arena->dummy_hitstun=9;
            ++arena->successful_hits;
        }
    }
    ++arena->ticks;
}

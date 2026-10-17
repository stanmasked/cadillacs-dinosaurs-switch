#include "dino_arena.h"
#include <stddef.h>

/* Original ROM-free fixed-60Hz training rules, unrelated to the Capcom game.
 * The default is an immobile dummy. X toggles optional deterministic sparring.
 * No heap, I/O, ROM, randomness, floating point, or copied CPS-1 logic.
 */
static int32_t clamp(int32_t v, int32_t lo, int32_t hi) {
    if (v<lo) return lo;
    if (v>hi) return hi;
    return v;
}
static int32_t distance(int32_t a,int32_t b) {
    return a>=b ? a-b : b-a;
}
static int32_t sign(int32_t n) { return (n>0)-(n<0); }

void dino_arena_reset(DinoArena *a) {
    if (!a) return;
    *a=(DinoArena){
        .x=90, .y=151, .z=0, .vz=0,
        .dummy_x=250, .dummy_y=151,
        .facing_right=1, .dummy_hp=3,
        .player_hp=5, .dummy_facing_right=0
    };
}

void dino_arena_step(DinoArena *a, uint32_t held, uint32_t pressed) {
    if (!a) return;
    held &= (DINO_ARENA_LEFT|DINO_ARENA_RIGHT|
             DINO_ARENA_UP|DINO_ARENA_DOWN);
    pressed &= (DINO_ARENA_ATTACK|DINO_ARENA_JUMP|DINO_ARENA_TOGGLE_SPAR);

    if (pressed&DINO_ARENA_TOGGLE_SPAR) {
        a->sparring=(uint8_t)!a->sparring;
        a->dummy_windup=0;
        a->dummy_cooldown=0;
        a->dummy_attack_frames=0;
        a->player_hitstun=0;
        a->player_invuln=0;
        if (a->sparring) {
            /* Start every sparring attempt with a fresh opponent,
             * independent of previous target-practice hits. */
            a->dummy_hp=3;
            a->dummy_x=250;
            a->dummy_y=151;
            a->player_hp=5;
            a->player_hits_taken=0;
        }
    }
    const int stunned=a->dummy_hitstun>0;
    if (a->dummy_hitstun) --a->dummy_hitstun;
    if (a->attack_frames) --a->attack_frames;
    if (a->attack_cooldown) --a->attack_cooldown;
    if (a->player_hitstun) --a->player_hitstun;
    if (a->player_invuln) --a->player_invuln;
    if (a->dummy_cooldown) --a->dummy_cooldown;
    if (a->dummy_attack_frames) --a->dummy_attack_frames;

    if (!a->player_hitstun && a->player_hp) {
        int dx=((held&DINO_ARENA_RIGHT)!=0)-((held&DINO_ARENA_LEFT)!=0);
        int dy=((held&DINO_ARENA_DOWN)!=0)-((held&DINO_ARENA_UP)!=0);
        int32_t target_x=clamp(a->x+2*dx,16,DINO_ARENA_WIDTH-16);
        int32_t target_y=clamp(a->y+dy,80,DINO_ARENA_HEIGHT-16);
        /* Horizontal body collision only in the same depth lane.
         * Opponents cannot pass through each other on one lane,
         * but passing in a different depth lane remains possible. */
        if (a->sparring && a->dummy_hp &&
            distance(target_y,a->dummy_y)<=10) {
            if (a->x<=a->dummy_x && target_x>a->dummy_x-14)
                target_x=a->dummy_x-14;
            if (a->x>a->dummy_x && target_x<a->dummy_x+14)
                target_x=a->dummy_x+14;
        }
        a->x=clamp(target_x,16,DINO_ARENA_WIDTH-16);
        a->y=target_y;
        if (dx) a->facing_right=(uint8_t)(dx>0);
        if ((pressed&DINO_ARENA_JUMP) && a->z==0 && a->vz==0)
            a->vz=8;
        if ((pressed&DINO_ARENA_ATTACK) && !a->attack_cooldown) {
            a->attack_frames=8;
            a->attack_cooldown=15;
            int32_t delta=a->dummy_x-a->x;
            int front=a->facing_right ? delta>=0 : delta<=0;
            if (a->dummy_hp && front && distance(a->dummy_x,a->x)<=38 &&
                distance(a->dummy_y,a->y)<=15 && a->z<=20) {
                --a->dummy_hp;
                a->dummy_hitstun=9;
                ++a->successful_hits;
                a->dummy_windup=0; /* successful hit interrupts attack */
            }
        }
    }

    if (a->z>0 || a->vz>0) {
        a->z+=a->vz;
        --a->vz;
        if (a->z<=0) { a->z=0; a->vz=0; }
    }

    if (a->sparring && a->dummy_hp && a->player_hp) {
        a->dummy_facing_right=(uint8_t)(a->x>a->dummy_x);
        if (stunned || a->dummy_hitstun) {
            a->dummy_windup=0;
        } else if (a->dummy_windup) {
            --a->dummy_windup;
            if (!a->dummy_windup) {
                a->dummy_cooldown=48;
                a->dummy_attack_frames=7;
                /* Telegraph must finish before damage. A late dodge
                 * across the lane, moving out of range or jumping high
                 * can avoid this single impact event. */
                if (distance(a->x,a->dummy_x)<=44 &&
                    distance(a->y,a->dummy_y)<=14 && a->z<=20 &&
                    !a->player_invuln) {
                    --a->player_hp;
                    ++a->player_hits_taken;
                    a->player_hitstun=11;
                    a->player_invuln=30;
                }
            }
        } else {
            int32_t delta=a->x-a->dummy_x;
            int32_t lane=a->y-a->dummy_y;
            if (distance(a->x,a->dummy_x)>36) {
                int32_t candidate=clamp(a->dummy_x+sign(delta),
                                        16,DINO_ARENA_WIDTH-16);
                if (distance(a->y,a->dummy_y)>10 ||
                    distance(candidate,a->x)>=14)
                    a->dummy_x=candidate;
            }
            if (distance(a->y,a->dummy_y)>5)
                a->dummy_y=clamp(a->dummy_y+sign(lane),
                                 80,DINO_ARENA_HEIGHT-16);
            if (!a->dummy_cooldown && distance(a->x,a->dummy_x)<=44 &&
                distance(a->y,a->dummy_y)<=14) {
                a->dummy_windup=12;
            }
        }
    }
    ++a->ticks;
}

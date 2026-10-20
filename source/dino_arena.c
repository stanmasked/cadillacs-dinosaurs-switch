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

/* Read-only presentation state: KO > hit reaction > strike >
 * aerial motion > movement > idle. Do not conflate graphical state
 * with collision, AI or combat decisions. */
DinoArenaPose dino_arena_player_pose(const DinoArena *a) {
    if (!a || !a->player_hp) return DINO_POSE_KO;
    if (a->player_hitstun) return DINO_POSE_HURT;
    if (a->attack_frames) return DINO_POSE_ATTACK;
    if (a->z || a->vz) return DINO_POSE_JUMP;
    if (a->player_moving) return DINO_POSE_WALK;
    return DINO_POSE_IDLE;
}
DinoArenaPose dino_arena_dummy_pose(const DinoArena *a) {
    if (!a || !a->dummy_hp) return DINO_POSE_KO;
    if (a->dummy_hitstun) return DINO_POSE_HURT;
    if (a->dummy_windup) return DINO_POSE_WINDUP;
    if (a->dummy_attack_frames) return DINO_POSE_ATTACK;
    if (a->dummy_moving) return DINO_POSE_WALK;
    return DINO_POSE_IDLE;
}
uint8_t dino_arena_pose_phase(const DinoArena *a) {
    return a ? (uint8_t)((a->ticks/6u)&1u) : 0u;
}

uint8_t dino_arena_counter_feedback_tick(uint8_t remaining,
                                         uint32_t events) {
    if (events&DINO_EVT_COUNTER) return 6u;
    return remaining ? (uint8_t)(remaining-1u) : 0u;
}

void dino_arena_step(DinoArena *a, uint32_t held, uint32_t pressed) {
    if (!a) return;
    held &= (DINO_ARENA_LEFT|DINO_ARENA_RIGHT|
             DINO_ARENA_UP|DINO_ARENA_DOWN);
    pressed &= (DINO_ARENA_ATTACK|DINO_ARENA_JUMP|DINO_ARENA_TOGGLE_SPAR|
                DINO_ARENA_COUNTER);
    /* One-shot events are valid for exactly this 60 Hz simulation step.
     * Short impact flashes persist independently of render frequency. */
    a->events=0;
    a->player_moving=0;
    a->dummy_moving=0;

    if (pressed&DINO_ARENA_TOGGLE_SPAR) {
        a->events|=DINO_EVT_SPAR_TOGGLE;
        a->sparring=(uint8_t)!a->sparring;
        a->dummy_windup=0;
        a->dummy_cooldown=0;
        a->dummy_attack_frames=0;
        a->player_hitstun=0;
        a->player_invuln=0;
        /* A new practice mode never inherits combo progress or VFX. */
        a->combo_hits=0;
        a->combo_timer=0;
        a->finisher_flash=0;
        a->dummy_impact_flash=0;
        a->player_impact_flash=0;
        if (a->sparring) {
            /* Start every sparring attempt with a fresh opponent,
             * independent of previous target-practice hits. */
            a->dummy_hp=3;
            a->dummy_hitstun=0;
            a->dummy_x=250;
            a->dummy_y=151;
            a->player_hp=5;
            a->player_hits_taken=0;
        }
    }
    /* A counter may start only if the player was truly actionable at the
     * BEGINNING of the 60 Hz tick. Countdown/landing below cannot turn a
     * still-stunned, still-attacking or airborne ZR/H press into a success. */
    const int counter_ready_at_tick_start=
        !a->player_hitstun && !a->attack_frames && a->z==0 && a->vz==0;
    const int stunned=a->dummy_hitstun>0;
    if (a->dummy_hitstun) --a->dummy_hitstun;
    if (a->attack_frames) --a->attack_frames;
    if (a->attack_cooldown) --a->attack_cooldown;
    if (a->player_hitstun) --a->player_hitstun;
    if (a->player_invuln) --a->player_invuln;
    if (a->dummy_cooldown) --a->dummy_cooldown;
    if (a->dummy_attack_frames) --a->dummy_attack_frames;
    if (a->finisher_flash) --a->finisher_flash;
    if (a->dummy_impact_flash) --a->dummy_impact_flash;
    if (a->player_impact_flash) --a->player_impact_flash;
    if (a->combo_timer) {
        --a->combo_timer;
        if (!a->combo_timer) a->combo_hits=0;
    }

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
        a->player_moving=(uint8_t)(a->x!=target_x || a->y!=target_y);
        a->x=clamp(target_x,16,DINO_ARENA_WIDTH-16);
        a->y=target_y;
        if (dx) a->facing_right=(uint8_t)(dx>0);
        if ((pressed&DINO_ARENA_JUMP) && a->z==0 && a->vz==0) {
            a->vz=8;
            a->events|=DINO_EVT_JUMP_START;
        }
        if ((pressed&DINO_ARENA_ATTACK) && !a->attack_cooldown) {
            a->events|=DINO_EVT_PLAYER_SWING;
            a->attack_frames=8;
            a->attack_cooldown=15;
            int32_t delta=a->dummy_x-a->x;
            int front=a->facing_right ? delta>=0 : delta<=0;
            if (a->dummy_hp && front && distance(a->dummy_x,a->x)<=38 &&
                distance(a->dummy_y,a->y)<=15 && a->z<=20) {
                --a->dummy_hp;
                ++a->successful_hits;
                a->events|=DINO_EVT_DUMMY_HIT;
                a->dummy_impact_flash=6;
                if (!a->dummy_hp) a->events|=DINO_EVT_DUMMY_KO;
                /* Only LANDED attacks advance the 24-tick, at-most-three
                 * combo. Misses / cooldown button presses never refresh it.
                 * The finisher fires once, exactly on the 2 -> 3 edge. */
                const int finisher=(a->combo_timer && a->combo_hits==2);
                if (!a->combo_timer) a->combo_hits=1;
                else if (a->combo_hits<3) ++a->combo_hits;
                a->combo_timer=24;
                a->dummy_hitstun=(uint8_t)(finisher?14:9);
                if (finisher) {
                    a->events|=DINO_EVT_FINISHER;
                    a->finisher_flash=10;
                    if (a->sparring) {
                        /* Apply a bounded single knockback event even if
                         * this finishing attack defeats the opponent. */
                        const int direction=a->facing_right?1:-1;
                        a->dummy_x=clamp(a->dummy_x+18*direction,
                                         16,DINO_ARENA_WIDTH-16);
                        a->dummy_moving=1;
                    }
                }
                a->dummy_windup=0; /* successful hit interrupts attack */
                if (!a->dummy_hp) a->dummy_attack_frames=0;
            }
        }
    }

    if (a->z>0 || a->vz>0) {
        a->z+=a->vz;
        --a->vz;
        if (a->z<=0) {
            a->z=0; a->vz=0;
            a->events|=DINO_EVT_LAND;
        }
    }

    /* Stage 225: wholly invented counter-defense for training sparring.
     * ZR/H is an EDGE (pressed), not a held invulnerability toggle.
     * The foe must already be telegraphing a strike. A grounded,
     * non-stunned player, facing the foe in the same lane and range,
     * may interrupt that windup. This never inflicts free damage and
     * cannot stack with jump/attack. The opponent receives its existing
     * 48-tick cooldown so a successful counter cannot be spammed.
     *
     * It adds no fields to the arena state, preserving all existing
     * deterministic demo/replay/PCM witness layouts and defaults. */
    if ((pressed&DINO_ARENA_COUNTER) &&
        !(pressed&(DINO_ARENA_ATTACK|DINO_ARENA_JUMP)) &&
        a->sparring && a->player_hp && a->dummy_hp &&
        counter_ready_at_tick_start &&
        a->dummy_windup && !stunned && !a->dummy_hitstun &&
        distance(a->x,a->dummy_x)<=44 &&
        distance(a->y,a->dummy_y)<=14 &&
        (a->facing_right ? a->dummy_x>=a->x : a->dummy_x<=a->x)) {
        a->dummy_windup=0;
        a->dummy_cooldown=48;
        a->dummy_hitstun=9;
        a->dummy_impact_flash=6;
        a->events|=DINO_EVT_COUNTER;
    }

    if (a->sparring && a->dummy_hp && a->player_hp) {
        const int32_t dummy_x_before=a->dummy_x;
        const int32_t dummy_y_before=a->dummy_y;
        a->dummy_facing_right=(uint8_t)(a->x>a->dummy_x);
        if (stunned || a->dummy_hitstun) {
            a->dummy_windup=0;
        } else if (a->dummy_windup) {
            --a->dummy_windup;
            if (!a->dummy_windup) {
                a->dummy_cooldown=48;
                a->dummy_attack_frames=7;
                a->events|=DINO_EVT_DUMMY_SWING;
                /* Telegraph must finish before damage. A late dodge
                 * across the lane, moving out of range or jumping high
                 * can avoid this single impact event. */
                if (distance(a->x,a->dummy_x)<=44 &&
                    distance(a->y,a->dummy_y)<=14 && a->z<=20 &&
                    !a->player_invuln) {
                    --a->player_hp;
                    ++a->player_hits_taken;
                    a->events|=DINO_EVT_PLAYER_HIT;
                    a->player_impact_flash=8;
                    if (!a->player_hp) a->events|=DINO_EVT_PLAYER_KO;
                    /* Taking an actual hit breaks active player combos. */
                    a->combo_hits=0;
                    a->combo_timer=0;
                    a->finisher_flash=0;
                    a->player_hitstun=11;
                    a->player_invuln=30;
                } else {
                    /* Rechecked at the actual impact tick: a later dodge,
                     * high jump or active invulnerability prevents damage. */
                    a->events|=DINO_EVT_DODGE;
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
        /* A finisher can displace the opponent before AI processing.
         * Preserve that event instead of clearing it after stun logic. */
        a->dummy_moving=(uint8_t)(a->dummy_moving ||
                                   a->dummy_x!=dummy_x_before ||
                                   a->dummy_y!=dummy_y_before);
    }
    ++a->ticks;
}

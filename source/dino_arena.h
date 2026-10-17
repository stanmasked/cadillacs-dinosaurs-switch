#ifndef DINO_ARENA_INCLUDED_H
#define DINO_ARENA_INCLUDED_H
#include <stdint.h>

/* An ORIGINAL ROM-FREE training-room prototype, not Cadillacs gameplay.
 * Coordinates are integer world pixels in a 384x224 diagnostic viewport.
 * No arcade ROM, original sprite or copied game physics needed.
 */
#define DINO_ARENA_WIDTH 384
#define DINO_ARENA_HEIGHT 224

enum {
    DINO_ARENA_LEFT = 1u,
    DINO_ARENA_RIGHT = 2u,
    DINO_ARENA_UP = 4u,
    DINO_ARENA_DOWN = 8u,
    DINO_ARENA_ATTACK = 16u,
    DINO_ARENA_JUMP = 32u,
    DINO_ARENA_TOGGLE_SPAR = 64u /* explicitly invented training AI */
};

typedef struct {
    int32_t x, y;             /* feet location in screen/world coordinates */
    int32_t z, vz;            /* upward jump offset and vertical velocity */
    int32_t dummy_x, dummy_y;
    uint32_t ticks, successful_hits;
    uint8_t facing_right;
    uint8_t dummy_hp;
    uint8_t dummy_hitstun;
    uint8_t attack_frames, attack_cooldown;
    /* Optional deterministic sparring: disabled after reset for original
     * stationary-target regression compatibility. Never arcade AI. */
    uint8_t sparring, player_hp, player_hitstun, player_invuln;
    uint8_t dummy_windup, dummy_cooldown, dummy_attack_frames;
    uint8_t dummy_facing_right, player_hits_taken;
    uint8_t player_moving, dummy_moving; /* displacement during most recent tick */
    /* Original training combo: consecutive LANDED attacks, 24-tick window.
     * 3rd hit triggers one knockback finisher in optional sparring mode. */
    uint8_t combo_hits, combo_timer, finisher_flash;
} DinoArena;

/* Visual state is derived from 60 Hz simulation, not from art or MAME.
 * All values are stable public integer constants for diagnostic playback. */
typedef enum {
    DINO_POSE_IDLE=0,
    DINO_POSE_WALK=1,
    DINO_POSE_JUMP=2,
    DINO_POSE_ATTACK=3,
    DINO_POSE_HURT=4,
    DINO_POSE_KO=5,
    DINO_POSE_WINDUP=6
} DinoArenaPose;

/* No gameplay state is changed by any of these read-only pose queries.
 * Visual phases cycle deterministically every six simulated ticks.
 * They are invented placeholder animations, NOT CPS-1 sprite timings. */
DinoArenaPose dino_arena_player_pose(const DinoArena *arena);
DinoArenaPose dino_arena_dummy_pose(const DinoArena *arena);
uint8_t dino_arena_pose_phase(const DinoArena *arena);

/* Core simulation uses no heap, I/O, ROM or platform-specific types. */
void dino_arena_reset(DinoArena *arena);
void dino_arena_step(DinoArena *arena, uint32_t held, uint32_t pressed);
#endif

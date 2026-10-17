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
} DinoArena;

/* Both routines use no heap, I/O, ROM or platform-specific types. */
void dino_arena_reset(DinoArena *arena);
void dino_arena_step(DinoArena *arena, uint32_t held, uint32_t pressed);
#endif

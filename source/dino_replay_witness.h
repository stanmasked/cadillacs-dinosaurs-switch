#ifndef DINO_REPLAY_WITNESS_H
#define DINO_REPLAY_WITNESS_H
#include "dino_arena.h"
#include <stdint.h>

/* Canonical, portable FNV-1a diagnostic hash for independent ROM-free
 * gameplay execution. Each 32-bit value is mixed in little-endian byte
 * order, irrespective of the host CPU's native byte order or padding.
 * This witnesses integer combat state and events, NOT GPU pixels/PCM.
 */
#define DINO_WITNESS_INIT UINT64_C(14695981039346656037)

uint64_t dino_replay_witness_tick(uint64_t hash,const DinoArena *arena);
#endif

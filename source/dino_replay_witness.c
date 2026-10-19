#include "dino_replay_witness.h"

#define WITNESS_PRIME UINT64_C(1099511628211)

static uint64_t mix32(uint64_t hash,uint32_t word) {
    for (unsigned i=0;i<4u;++i) {
        hash^=(uint8_t)(word>>(8u*i));
        hash*=WITNESS_PRIME;
    }
    return hash;
}

uint64_t dino_replay_witness_tick(uint64_t hash,const DinoArena *a) {
    if (!a) return hash;
    /* Fixed schema v1, explicit order, no C struct serialization. */
    hash=mix32(hash,a->ticks);
    hash=mix32(hash,(uint32_t)a->x);
    hash=mix32(hash,(uint32_t)a->y);
    hash=mix32(hash,(uint32_t)a->z);
    hash=mix32(hash,(uint32_t)a->vz);
    hash=mix32(hash,(uint32_t)a->dummy_x);
    hash=mix32(hash,(uint32_t)a->dummy_y);
    hash=mix32(hash,a->successful_hits);
    hash=mix32(hash,a->events);
    hash=mix32(hash,a->player_hp);
    hash=mix32(hash,a->dummy_hp);
    hash=mix32(hash,a->combo_hits);
    hash=mix32(hash,a->sparring);
    hash=mix32(hash,(uint32_t)dino_arena_player_pose(a));
    hash=mix32(hash,(uint32_t)dino_arena_dummy_pose(a));
    return hash;
}

#include "dino_pcm_witness.h"
#define FNV64_PRIME UINT64_C(1099511628211)

uint64_t dino_pcm_witness_feed(uint64_t hash,
                               const int16_t *stereo,
                               size_t frames) {
    if (!stereo || frames>DINO_PCM_WITNESS_MAX_FRAMES)
        return hash; /* invalid input never changes witness */
    for (size_t i=0;i<frames*2u;++i) {
        const uint16_t v=(uint16_t)stereo[i];
        hash^=(uint8_t)v;
        hash*=FNV64_PRIME;
        hash^=(uint8_t)(v>>8);
        hash*=FNV64_PRIME;
    }
    return hash;
}

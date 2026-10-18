#ifndef DINO_PCM_WITNESS_H
#define DINO_PCM_WITNESS_H
#include <stddef.h>
#include <stdint.h>
/* Portable 16-bit signed stereo PCM witness. Hash every generated sample,
 * in explicit little-endian byte order, BEFORE device submission.
 * It is not evidence of actually audible sound or audout device delivery.
 */
#define DINO_PCM_WITNESS_INIT UINT64_C(14695981039346656037)
#define DINO_PCM_WITNESS_MAX_FRAMES 800u
uint64_t dino_pcm_witness_feed(uint64_t hash,
                               const int16_t *stereo,
                               size_t frames);
#endif

#ifndef CPS1_SEQUENCE_INCLUDED_H
#define CPS1_SEQUENCE_INCLUDED_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "cps1_scene.h"

/* Independent single-frame captures, not a game emulator or save states.
 * CPS1SEQ1: magic[8], count(u16le), fps(u16le), crc32(u32le), reserved(u32le),
 * followed by count consecutive CPS1SCN1 blobs. Content stays user-local.
 */
#define CPS1_SEQUENCE_HEADER_BYTES 20u
#define CPS1_SEQUENCE_MAX_FRAMES 120u
#define CPS1_SEQUENCE_MAX_BYTES (CPS1_SEQUENCE_HEADER_BYTES +                                   CPS1_SEQUENCE_MAX_FRAMES * CPS1_SCENE_FILE_BYTES)

typedef struct {
    const uint8_t *blob;  /* caller owns data, must remain allocated */
    uint16_t frame_count;
    uint16_t fps;
} Cps1Sequence;

typedef struct {
    uint32_t index;
    uint32_t remainder;  /* 0..119, unit: half-60Hz ticks */
    unsigned speed_num;  /* 1 = half, 2 = normal, 4 = double speed */
    bool paused;
} Cps1Playback;

bool cps1_sequence_decode(const uint8_t *data, size_t length,
                          Cps1Sequence *out);
bool cps1_sequence_frame(const Cps1Sequence *sequence, unsigned index,
                         Cps1Scene *out);
void cps1_playback_init(Cps1Playback *playback);
bool cps1_playback_advance(Cps1Playback *playback,
                           const Cps1Sequence *sequence, uint32_t ticks60);
bool cps1_playback_step(Cps1Playback *playback,
                        const Cps1Sequence *sequence, int direction);
void cps1_playback_speed(Cps1Playback *playback, int direction);
#endif

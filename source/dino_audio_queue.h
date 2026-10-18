#ifndef DINO_AUDIO_QUEUE_INCLUDED_H
#define DINO_AUDIO_QUEUE_INCLUDED_H
#include <stdbool.h>
#include <stdint.h>

/* Portable and allocation-free scheduling policy for libnx PCM buffers.
 * Four independent aligned memory pages, but at most TWO pages queued to
 * the device (approximately 33 ms of PCM at 60Hz, not an observed latency).
 * When both are busy, synthetic audio time progresses but no stale buffer
 * is allowed to accumulate. This module never touches an audio device.
 */
#define DINO_AUDIO_QUEUE_SLOTS 4u
#define DINO_AUDIO_QUEUE_MAX_PENDING 2u

typedef struct {
    uint8_t busy[DINO_AUDIO_QUEUE_SLOTS];
    uint8_t pending;
    uint32_t submitted;
    uint32_t skipped;
    uint32_t released;
} DinoAudioQueue;

void dino_audio_queue_reset(DinoAudioQueue *queue);
/* -1 means queue full or invalid pointer; read-only query. */
int dino_audio_queue_pick(const DinoAudioQueue *queue);
/* Mark a buffer ONLY after audoutAppendAudioOutBuffer succeeds. */
bool dino_audio_queue_submit(DinoAudioQueue *queue, unsigned index);
/* Reject unknown/duplicate release indices without damaging bookkeeping. */
bool dino_audio_queue_release(DinoAudioQueue *queue, unsigned index);
void dino_audio_queue_skip(DinoAudioQueue *queue);
#endif

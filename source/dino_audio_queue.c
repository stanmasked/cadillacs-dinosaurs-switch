#include "dino_audio_queue.h"

void dino_audio_queue_reset(DinoAudioQueue *q) {
    if (!q) return;
    *q=(DinoAudioQueue){0};
}

int dino_audio_queue_pick(const DinoAudioQueue *q) {
    if (!q || q->pending>=DINO_AUDIO_QUEUE_MAX_PENDING) return -1;
    for (unsigned i=0;i<DINO_AUDIO_QUEUE_SLOTS;++i)
        if (!q->busy[i]) return (int)i;
    return -1;
}

bool dino_audio_queue_submit(DinoAudioQueue *q, unsigned index) {
    if (!q || index>=DINO_AUDIO_QUEUE_SLOTS ||
        q->pending>=DINO_AUDIO_QUEUE_MAX_PENDING || q->busy[index])
        return false;
    q->busy[index]=1;
    ++q->pending;
    ++q->submitted;
    return true;
}

bool dino_audio_queue_release(DinoAudioQueue *q, unsigned index) {
    if (!q || index>=DINO_AUDIO_QUEUE_SLOTS ||
        !q->busy[index] || !q->pending) return false;
    q->busy[index]=0;
    --q->pending;
    ++q->released;
    return true;
}

void dino_audio_queue_skip(DinoAudioQueue *q) {
    if (q) ++q->skipped;
}

bool dino_audio_queue_snapshot(const DinoAudioQueue *q,
                               DinoAudioQueueStats *out) {
    if (!q || !out || q->pending>DINO_AUDIO_QUEUE_MAX_PENDING)
        return false;
    uint32_t mask=0, counted=0;
    for (unsigned i=0;i<DINO_AUDIO_QUEUE_SLOTS;++i) {
        if (q->busy[i]>1) return false;
        if (q->busy[i]) {
            mask|=1u<<i;
            ++counted;
        }
    }
    /* An inconsistent queue must not publish invented 'healthy' counts.
     * Arithmetic is modulo 2^32, matching uint32_t lifetime counters. */
    if (counted!=q->pending ||
        (uint32_t)(q->submitted-q->released)!=(uint32_t)q->pending)
        return false;
    *out=(DinoAudioQueueStats){
        .busy_mask=mask, .pending=q->pending,
        .submitted=q->submitted, .released=q->released,
        .skipped=q->skipped
    };
    return true;
}

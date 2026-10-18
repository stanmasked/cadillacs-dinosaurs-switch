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

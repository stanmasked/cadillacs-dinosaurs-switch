#include "dino_audio_slots.h"
void dino_audio_slots_reset(DinoAudioSlots *s) {
    if (!s) return;
    *s=(DinoAudioSlots){0};
}
int dino_audio_slots_available(const DinoAudioSlots *s) {
    if (!s) return -1;
    for (unsigned i=0;i<DINO_AUDIO_SLOT_COUNT;++i)
        if (!s->busy[i]) return (int)i;
    return -1;
}
bool dino_audio_slots_submit(DinoAudioSlots *s,unsigned index) {
    if (!s || index>=DINO_AUDIO_SLOT_COUNT || s->busy[index]) return false;
    s->busy[index]=1;
    ++s->submitted;
    return true;
}
bool dino_audio_slots_release(DinoAudioSlots *s,unsigned index) {
    if (!s) return false;
    if (index>=DINO_AUDIO_SLOT_COUNT || !s->busy[index]) {
        ++s->invalid_releases;
        return false;
    }
    s->busy[index]=0;
    ++s->released;
    return true;
}
void dino_audio_slots_skip(DinoAudioSlots *s) {
    if (s) ++s->skipped;
}

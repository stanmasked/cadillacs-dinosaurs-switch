#ifndef DINO_AUDIO_SLOTS_H
#define DINO_AUDIO_SLOTS_H
#include <stdbool.h>
#include <stdint.h>
/* ROM-free, pure C, bounded four-page PCM ownership state machine.
 * Never reuse a submitted page until its release is acknowledged. */
#define DINO_AUDIO_SLOT_COUNT 4u
typedef struct {
    uint8_t busy[DINO_AUDIO_SLOT_COUNT];
    uint32_t submitted, released, skipped, invalid_releases;
} DinoAudioSlots;
void dino_audio_slots_reset(DinoAudioSlots *slots);
int dino_audio_slots_available(const DinoAudioSlots *slots);
bool dino_audio_slots_submit(DinoAudioSlots *slots, unsigned index);
bool dino_audio_slots_release(DinoAudioSlots *slots, unsigned index);
void dino_audio_slots_skip(DinoAudioSlots *slots);
#endif

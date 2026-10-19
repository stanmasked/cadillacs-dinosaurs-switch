#ifndef DINO_SFX_INCLUDED_H
#define DINO_SFX_INCLUDED_H
#include <stddef.h>
#include <stdint.h>
/* Purely ORIGINAL event synthesizer: no ROM audio or prerecorded samples.
 * 48 kHz interleaved 16-bit stereo; exactly 800 samples per 60 Hz game tick.
 * Host C and Nintendo Switch use the identical code and exact integer math.
 */
#define DINO_SFX_RATE 48000u
#define DINO_SFX_TICK_FRAMES 800u
#define DINO_SFX_VOICES 6u

typedef struct {
    uint32_t phase, phase_step, rng;
    uint32_t remaining, total;
    int32_t gain;
    int16_t pan;       /* signed -128..+128 */
    uint8_t wave;      /* 0 triangle, 1 noise */
    uint8_t priority;
} DinoSfxVoice;

typedef struct {
    DinoSfxVoice voices[DINO_SFX_VOICES];
    uint32_t ticks;
    uint32_t launched;
    uint32_t dropped;
} DinoSfx;

void dino_sfx_reset(DinoSfx *s);
void dino_sfx_events(DinoSfx *s, uint32_t events);
void dino_sfx_render_tick(DinoSfx *s, int16_t *interleaved_stereo,
                          size_t frame_count);
unsigned dino_sfx_active_voices(const DinoSfx *s);
#endif

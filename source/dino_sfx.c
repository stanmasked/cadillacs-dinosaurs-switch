#include "dino_sfx.h"
#include "dino_arena.h"

/* Integer-only portable synth for a ROM-free training game.
 * Its tonal intervals and noises were invented for this prototype.
 * No libm, samples, malloc, system clock, device handles or file reads.
 */
enum { WAVE_TRIANGLE=0, WAVE_NOISE=1 };
typedef struct {
    uint32_t event;
    uint16_t hz, ticks;
    uint16_t gain;
    int16_t pan;
    uint8_t wave, priority;
} SoundDef;

/* Low -> high priority: when six voices fill, a new stronger event
 * replaces the least important voice, but never its equal or stronger.
 * This preserves hits and KOs when multiple flags occur together.
 */
static const SoundDef sounds[] = {
    {DINO_EVT_SPAR_TOGGLE, 530,  5, 1100,    0, WAVE_TRIANGLE, 1},
    {DINO_EVT_LAND,         118,  6, 1000,    0, WAVE_NOISE,    2},
    {DINO_EVT_JUMP_START,   510,  7, 1200,  -28, WAVE_TRIANGLE, 2},
    {DINO_EVT_PLAYER_SWING, 260,  5, 1150,  -36, WAVE_NOISE,    3},
    {DINO_EVT_DODGE,        710,  8, 1050,    0, WAVE_TRIANGLE, 3},
    {DINO_EVT_DUMMY_SWING,  196,  7, 1300,   36, WAVE_NOISE,    3},
    /* Original Stage 227 counter confirmation: one short pitched cue.
     * It is never triggered during the legacy demo (no counter input).
     * Moderate priority keeps existing damage/KO cues dominant. */
    {DINO_EVT_COUNTER,      820,  6, 1350,    0, WAVE_TRIANGLE, 4},
    {DINO_EVT_DUMMY_HIT,    132, 10, 1700,   44, WAVE_NOISE,    5},
    {DINO_EVT_PLAYER_HIT,   114, 12, 1900,  -44, WAVE_NOISE,    6},
    {DINO_EVT_FINISHER,     108, 14, 2100,   16, WAVE_TRIANGLE, 7},
    {DINO_EVT_DUMMY_KO,      76, 20, 2300,   34, WAVE_TRIANGLE, 8},
    {DINO_EVT_PLAYER_KO,     68, 20, 2300,  -34, WAVE_TRIANGLE, 8},
};

void dino_sfx_reset(DinoSfx *s) {
    if (!s) return;
    *s=(DinoSfx){0};
}

unsigned dino_sfx_active_voices(const DinoSfx *s) {
    if (!s) return 0;
    unsigned active=0;
    for (size_t i=0;i<DINO_SFX_VOICES;++i)
        if (s->voices[i].remaining) ++active;
    return active;
}

void dino_sfx_events(DinoSfx *s, uint32_t events) {
    if (!s) return;
    for (size_t i=0;i<sizeof(sounds)/sizeof(sounds[0]);++i) {
        const SoundDef *def=&sounds[i];
        if (!(events&def->event)) continue;
        size_t slot=DINO_SFX_VOICES;
        uint8_t min_priority=255;
        size_t quietest=0;
        for (size_t j=0;j<DINO_SFX_VOICES;++j) {
            if (!s->voices[j].remaining) { slot=j; break; }
            if (s->voices[j].priority<min_priority) {
                min_priority=s->voices[j].priority;
                quietest=j;
            }
        }
        if (slot==DINO_SFX_VOICES) {
            if (def->priority<=min_priority) {
                ++s->dropped;
                continue;
            }
            slot=quietest;
        }
        DinoSfxVoice *voice=&s->voices[slot];
        uint32_t duration=(uint32_t)def->ticks*DINO_SFX_TICK_FRAMES;
        *voice=(DinoSfxVoice){
            .phase=0, .phase_step=(uint32_t)(((uint64_t)def->hz<<32)/
                                           DINO_SFX_RATE),
            .rng=0xa341316cu ^ (def->event*0x9e3779b9u),
            .remaining=duration, .total=duration,
            .gain=def->gain, .pan=def->pan, .wave=def->wave,
            .priority=def->priority
        };
        ++s->launched;
    }
}

static int16_t clipped(int32_t value) {
    if (value>32767) value=32767;
    if (value<-32768) value=-32768;
    return (int16_t)value;
}

void dino_sfx_render_tick(DinoSfx *s, int16_t *stereo, size_t frames) {
    if (!s || !stereo || frames>DINO_SFX_TICK_FRAMES) return;
    for (size_t frame=0;frame<frames;++frame) {
        int32_t left=0, right=0;
        for (size_t j=0;j<DINO_SFX_VOICES;++j) {
            DinoSfxVoice *v=&s->voices[j];
            if (!v->remaining) continue;
            int32_t wave;
            if (v->wave==WAVE_NOISE) {
                /* Portable xorshift noise, seeded only by event identity. */
                v->rng^=v->rng<<13;
                v->rng^=v->rng>>17;
                v->rng^=v->rng<<5;
                wave=(int32_t)(v->rng>>16)-32768;
            } else {
                uint32_t p=v->phase>>16;
                wave=p<32768u ? (int32_t)(p*2u)-32768 :
                                 98304-(int32_t)(p*2u);
            }
            /* 64-bit intermediate prevents overflow for a long envelope.
             * Peak individual voice <= 2300; all six stay far below clip.
             */
            int32_t signal=(int32_t)(((int64_t)wave*v->gain*v->remaining)/
                                     ((int64_t)32768*v->total));
            left+=(signal*(128-v->pan))/128;
            right+=(signal*(128+v->pan))/128;
            v->phase+=v->phase_step;
            --v->remaining;
        }
        stereo[2*frame]=clipped(left);
        stereo[2*frame+1]=clipped(right);
    }
    if (frames==DINO_SFX_TICK_FRAMES) ++s->ticks;
}

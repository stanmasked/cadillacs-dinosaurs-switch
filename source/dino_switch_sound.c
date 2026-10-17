#include "dino_switch_sound.h"
#include "dino_sfx.h"
#include <switch.h>
#include <string.h>

enum { AUDIO_SLOTS=4, AUDIO_CAPACITY=4096 };
static DinoSfx s_synth;
static AudioOutBuffer s_buffers[AUDIO_SLOTS];
static bool s_busy[AUDIO_SLOTS];
/* Stereo int16 × 800 samples = 3200 bytes in 4096-byte aligned storage.
 * No buffer may be rewritten before the audio service releases it.
 */
static uint8_t s_pcm[AUDIO_SLOTS][AUDIO_CAPACITY]
    __attribute__((aligned(0x1000)));
static int16_t s_discard[DINO_SFX_TICK_FRAMES*2];
static bool s_initialized, s_started;

void dino_switch_sound_close(void) {
    if (s_started) {
        (void)audoutStopAudioOut();
        s_started=false;
    }
    if (s_initialized) {
        audoutExit();
        s_initialized=false;
    }
    memset(s_busy,0,sizeof(s_busy));
}

bool dino_switch_sound_open(void) {
    dino_sfx_reset(&s_synth);
    if (s_initialized) return s_started;
    if (R_FAILED(audoutInitialize())) return false;
    s_initialized=true;
    if (audoutGetSampleRate()!=DINO_SFX_RATE ||
        audoutGetChannelCount()!=2 ||
        audoutGetPcmFormat()!=PcmFormat_Int16 ||
        R_FAILED(audoutStartAudioOut())) {
        dino_switch_sound_close();
        return false;
    }
    s_started=true;
    for (unsigned i=0;i<AUDIO_SLOTS;++i) {
        s_buffers[i]=(AudioOutBuffer){
            .buffer=s_pcm[i],
            .buffer_size=AUDIO_CAPACITY,
            .data_size=DINO_SFX_TICK_FRAMES*2*sizeof(int16_t)
        };
        s_busy[i]=false;
    }
    return true;
}

void dino_switch_sound_step(uint32_t events) {
    /* Even when no hardware buffer is available, the sound envelopes
     * advance exactly once per simulated tick, never in rendering time. */
    dino_sfx_events(&s_synth,events);
    int slot=-1;
    if (s_started) {
        for (unsigned n=0;n<AUDIO_SLOTS;++n) {
            AudioOutBuffer *released=NULL;
            u32 released_count=0;
            if (R_FAILED(audoutGetReleasedAudioOutBuffer(
                    &released,&released_count))) {
                dino_switch_sound_close();
                break;
            }
            if (!released_count) break;
            for (unsigned i=0;i<AUDIO_SLOTS;++i)
                if (released==&s_buffers[i]) s_busy[i]=false;
        }
        if (s_started)
            for (unsigned i=0;i<AUDIO_SLOTS;++i)
                if (!s_busy[i]) { slot=(int)i; break; }
    }
    int16_t *output=slot>=0 ? (int16_t*)s_pcm[slot] : s_discard;
    dino_sfx_render_tick(&s_synth,output,DINO_SFX_TICK_FRAMES);
    if (slot>=0) {
        /* The audout service accesses this page-aligned PCM memory. */
        armDCacheFlush(s_pcm[slot],AUDIO_CAPACITY);
        if (R_SUCCEEDED(audoutAppendAudioOutBuffer(&s_buffers[slot])))
            s_busy[slot]=true;
        else dino_switch_sound_close(); /* silent fallback, never block */
    }
}

#include "dino_switch_sound.h"
#include "dino_sfx.h"
#include "dino_audio_queue.h"
#include <switch.h>
#include <string.h>

enum { AUDIO_SLOTS=4, AUDIO_CAPACITY=4096 };
static DinoSfx s_synth;
static AudioOutBuffer s_buffers[AUDIO_SLOTS];
static DinoAudioQueue s_queue;
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
    dino_audio_queue_reset(&s_queue);
}

bool dino_switch_sound_open(void) {
    /* Idempotent initialization must not reset a live effect envelope. */
    if (s_initialized) return s_started;
    dino_sfx_reset(&s_synth);
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
    dino_audio_queue_reset(&s_queue);
    for (unsigned i=0;i<AUDIO_SLOTS;++i) {
        s_buffers[i]=(AudioOutBuffer){
            .buffer=s_pcm[i],
            .buffer_size=AUDIO_CAPACITY,
            .data_size=DINO_SFX_TICK_FRAMES*2*sizeof(int16_t)
        };
    }
    return true;
}

void dino_switch_sound_step(uint32_t events) {
    /* Envelopes progress once per 60Hz game tick, even if a stalled
     * console is unable to accept another PCM buffer this frame. */
    dino_sfx_events(&s_synth,events);
    int slot=-1;
    if (s_started) {
        for (unsigned n=0;n<AUDIO_SLOTS;++n) {
            AudioOutBuffer *released=NULL;
            u32 count=0;
            if (R_FAILED(audoutGetReleasedAudioOutBuffer(&released,&count))) {
                dino_switch_sound_close();
                break;
            }
            if (!count) break;
            /* The libnx API returns one buffer pointer, not an array.
             * Multiple releases in one result cannot be accounted for
             * safely by this adapter: fail closed to preserve ownership. */
            if (count!=1 || !released) {
                dino_switch_sound_close();
                break;
            }
            /* A foreign or duplicate release must never make an in-flight
             * PCM page available for rewriting: stop the audio backend. */
            bool known=false;
            for (unsigned i=0;i<AUDIO_SLOTS;++i) {
                if (released!=&s_buffers[i]) continue;
                known=dino_audio_queue_release(&s_queue,i);
                break;
            }
            if (!known) {
                dino_switch_sound_close();
                break;
            }
        }
        if (s_started) slot=dino_audio_queue_pick(&s_queue);
    }
    if (slot<0) dino_audio_queue_skip(&s_queue);
    int16_t *output=slot>=0 ? (int16_t*)s_pcm[slot] : s_discard;
    dino_sfx_render_tick(&s_synth,output,DINO_SFX_TICK_FRAMES);
    if (slot>=0) {
        /* Flush the full 0x1000 page before handing it to audout.
         * Exactly 3200 bytes contain the active stereo PCM frame. */
        armDCacheFlush(s_pcm[slot],AUDIO_CAPACITY);
        if (R_FAILED(audoutAppendAudioOutBuffer(&s_buffers[slot])) ||
            !dino_audio_queue_submit(&s_queue,(unsigned)slot))
            dino_switch_sound_close(); /* no wait/no stale PCM backlog */
    }
}

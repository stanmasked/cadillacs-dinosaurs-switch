#include "dino_switch_sound.h"
#include "dino_sfx.h"
#include "dino_pcm_witness.h"
#include "dino_audio_queue.h"
#include <switch.h>

enum { AUDIO_SLOTS=4, AUDIO_CAPACITY=4096 };
_Static_assert(AUDIO_SLOTS==DINO_AUDIO_QUEUE_SLOTS,
               "Sound backend slot count must match admission policy");
_Static_assert(DINO_SFX_TICK_FRAMES*2u*sizeof(int16_t)<=AUDIO_CAPACITY,
               "A stereo tick must fit in one aligned audio page");
_Static_assert(AUDIO_CAPACITY==0x1000,
               "libnx audout pages must retain 4096-byte alignment");
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
static uint32_t s_audio_errors, s_simulated_ticks;
static uint32_t s_skip_full, s_skip_inactive, s_skip_unexpected;
static uint32_t s_current_skip_streak, s_max_skip_streak;
static uint64_t s_pcm_witness=DINO_PCM_WITNESS_INIT;

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
    s_pcm_witness=DINO_PCM_WITNESS_INIT;
    if (R_FAILED(audoutInitialize())) {
        ++s_audio_errors;
        return false;
    }
    s_initialized=true;
    if (audoutGetSampleRate()!=DINO_SFX_RATE ||
        audoutGetChannelCount()!=2 ||
        audoutGetPcmFormat()!=PcmFormat_Int16 ||
        R_FAILED(audoutStartAudioOut())) {
        ++s_audio_errors;
        dino_switch_sound_close();
        return false;
    }
    s_started=true;
    dino_audio_queue_reset(&s_queue);
    /* The queue's own counters reset here; keep the cause counters
     * on the same lifecycle so reason sums can be checked. */
    s_skip_full=0;
    s_skip_inactive=0;
    s_skip_unexpected=0;
    s_current_skip_streak=0;
    s_max_skip_streak=0;
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
    ++s_simulated_ticks;
    dino_sfx_events(&s_synth,events);
    int slot=-1;
    if (s_started) {
        for (unsigned n=0;n<AUDIO_SLOTS;++n) {
            AudioOutBuffer *released=NULL;
            u32 count=0;
            if (R_FAILED(audoutGetReleasedAudioOutBuffer(&released,&count))) {
                ++s_audio_errors;
                dino_switch_sound_close();
                break;
            }
            if (!count) break;
            /* The libnx API returns one buffer pointer, not an array.
             * Multiple releases in one result cannot be accounted for
             * safely by this adapter: fail closed to preserve ownership. */
            if (count!=1 || !released) {
                ++s_audio_errors;
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
                ++s_audio_errors;
                dino_switch_sound_close();
                break;
            }
        }
        if (s_started) slot=dino_audio_queue_pick(&s_queue);
    }
    if (slot<0) {
        /* Do not change page policy or reorder PCM: diagnostic only. */
        dino_audio_queue_skip(&s_queue);
        if (!s_started) ++s_skip_inactive;
        else if (s_queue.pending>=DINO_AUDIO_QUEUE_MAX_PENDING)
            ++s_skip_full;
        else ++s_skip_unexpected;
        ++s_current_skip_streak;
        if (s_current_skip_streak>s_max_skip_streak)
            s_max_skip_streak=s_current_skip_streak;
    } else {
        s_current_skip_streak=0;
    }
    int16_t *output=slot>=0 ? (int16_t*)s_pcm[slot] : s_discard;
    dino_sfx_render_tick(&s_synth,output,DINO_SFX_TICK_FRAMES);
    /* Measure generated samples even if audout is stopped, full or slow.
     * Device delivery / audibility is deliberately a separate question. */
    s_pcm_witness=dino_pcm_witness_feed(
        s_pcm_witness,output,DINO_SFX_TICK_FRAMES);
    if (slot>=0) {
        /* Flush the full 0x1000 page before handing it to audout.
         * Exactly 3200 bytes contain the active stereo PCM frame. */
        armDCacheFlush(s_pcm[slot],AUDIO_CAPACITY);
        if (R_FAILED(audoutAppendAudioOutBuffer(&s_buffers[slot])) ||
            !dino_audio_queue_submit(&s_queue,(unsigned)slot)) {
            ++s_audio_errors;
            dino_switch_sound_close(); /* no wait/no stale PCM backlog */
        }
    }
}

void dino_switch_sound_diagnostics(DinoSoundDiagnostics *out) {
    if (!out) return;
    *out=(DinoSoundDiagnostics){0};
    out->simulated_ticks=s_simulated_ticks;
    out->audio_errors=s_audio_errors;
    out->active=(uint8_t)s_started;
    out->full_queue_skips=s_skip_full;
    out->inactive_backend_skips=s_skip_inactive;
    out->unexpected_slot_skips=s_skip_unexpected;
    out->max_consecutive_skips=s_max_skip_streak;
    DinoAudioQueueStats snapshot;
    if (dino_audio_queue_snapshot(&s_queue,&snapshot)) {
        out->queue_valid=1;
        out->pending=snapshot.pending;
        out->submitted=snapshot.submitted;
        out->released=snapshot.released;
        out->skipped=snapshot.skipped;
    }
}

uint64_t dino_switch_sound_pcm_witness(void) {
    return s_pcm_witness;
}
uint32_t dino_switch_sound_pcm_ticks(void) {
    return s_synth.ticks;
}

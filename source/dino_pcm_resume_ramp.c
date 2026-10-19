#include "dino_pcm_resume_ramp.h"

#include <limits.h>

/* Pure integer arithmetic with truncation toward zero, no interpolation
 * outside the initial ramp. For 48kHz, 96 frames == 2 ms.
 * Multiply in signed 64-bit to avoid overflow for all size_t variants.
 * Reject oversized fade factors before writing ANY output sample. */
bool dino_pcm_resume_ramp_apply(int16_t *stereo, size_t frames,
                                size_t attack_frames) {
    if (!stereo || !frames || attack_frames == 0 ||
        attack_frames > frames || attack_frames > INT32_MAX ||
        frames > SIZE_MAX / 2u) {
        return false;
    }
    for (size_t i=0; i<attack_frames; ++i) {
        const int64_t gain=(int64_t)(i+1u);
        const int64_t denom=(int64_t)attack_frames;
        const size_t offset=2u*i;
        /* gain<=denom guarantees the magnitude is never amplified. */
        stereo[offset]=(int16_t)(((int64_t)stereo[offset]*gain)/denom);
        stereo[offset+1u]=
            (int16_t)(((int64_t)stereo[offset+1u]*gain)/denom);
    }
    return true;
}

/* A single pending edge survives any number of successive full-queue
 * misses, and is consumed only after the next VALID PCM admission.
 * Saturate a diagnostic counter rather than silently wrapping it. */
void dino_pcm_resume_ramp_reset(DinoPcmResumeRampState *state) {
    if (!state) return;
    state->pending=false;
    state->applied=0;
}

void dino_pcm_resume_ramp_note_full_skip(DinoPcmResumeRampState *state) {
    if (state) state->pending=true;
}

bool dino_pcm_resume_ramp_before_submit(DinoPcmResumeRampState *state,
                                        int16_t *stereo, size_t frames,
                                        size_t attack_frames) {
    if (!state || !state->pending) return false;
    if (!dino_pcm_resume_ramp_apply(stereo,frames,attack_frames)) return false;
    state->pending=false;
    if (state->applied<UINT32_MAX) ++state->applied;
    return true;
}

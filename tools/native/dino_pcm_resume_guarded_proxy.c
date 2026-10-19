#include "dino_pcm_resume_guarded_proxy.h"

#include <limits.h>

/* Same exact integer truncation-toward-zero as the optional C output
 * attack. This pure screening routine changes no sample, queue or clock.
 * At most 800 game-tick frames in the real selftest; malformed/general
 * callers are also bounded against overflow before any PCM read. */
static int32_t dino_abs_step(int16_t a, int16_t b) {
    const int32_t delta=(int32_t)a-(int32_t)b;
    return delta<0 ? -delta : delta;
}

bool dino_pcm_resume_guarded_proxy_would_help(
    const int16_t previous_submitted_stereo[2],
    const int16_t *next_interleaved_stereo,
    size_t frames,
    size_t attack_frames) {
    if (!previous_submitted_stereo || !next_interleaved_stereo ||
        !frames || !attack_frames || attack_frames>frames ||
        attack_frames>(size_t)INT32_MAX || frames>SIZE_MAX/2u)
        return false;

    int32_t original_max_all=0;
    int32_t ramp_max_all=0;
    for (unsigned channel=0; channel<2u; ++channel) {
        int16_t original_prior=previous_submitted_stereo[channel];
        int16_t ramp_prior=previous_submitted_stereo[channel];
        int32_t original_max=0, ramp_max=0;
        for (size_t f=0; f<attack_frames; ++f) {
            const int16_t original=next_interleaved_stereo[2u*f+channel];
            const int64_t scaled=(int64_t)original*(int64_t)(f+1u)/
                                 (int64_t)attack_frames;
            const int16_t ramped=(int16_t)scaled;
            const int32_t plain_jump=dino_abs_step(original,original_prior);
            const int32_t ramp_jump=dino_abs_step(ramped,ramp_prior);
            /* A lower peak INSIDE the attack is insufficient when the
             * FIRST new sample introduces a previously absent pop. */
            if (f==0u && ramp_jump>plain_jump)
                return false;
            if (plain_jump>original_max) original_max=plain_jump;
            if (ramp_jump>ramp_max) ramp_max=ramp_jump;
            original_prior=original;
            ramp_prior=ramped;
        }
        if (ramp_max>original_max)
            return false;
        if (original_max>original_max_all)
            original_max_all=original_max;
        if (ramp_max>ramp_max_all)
            ramp_max_all=ramp_max;
    }
    return ramp_max_all<original_max_all;
}

#ifndef DINO_PCM_RESUME_RAMP_INCLUDED_H
#define DINO_PCM_RESUME_RAMP_INCLUDED_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Experimental ROM-free stereo PCM edge treatment. No extra queued pages,
 * no audio device calls, no waits, no resampling and no change to the 60Hz
 * synthesizer. Must be compiled into the sound path ONLY for explicitly
 * selected selftest builds. A 96-frame linear attack is 2ms at 48kHz.
 *
 * IMPORTANT: a numerical ramp is not evidence of improved audible sound
 * quality, eliminated glitches or a measured speaker output latency.
 */
#define DINO_PCM_RESUME_RAMP_FRAMES 96u

/* In-place, interleaved signed 16-bit stereo. Scales only the first
 * 'attack_frames' frames by (frame_index+1)/attack_frames. Leaves the
 * remainder byte-identical. False on malformed arguments; no writes.
 */
bool dino_pcm_resume_ramp_apply(int16_t *stereo, size_t frames,
                                size_t attack_frames);

/* Portable one-shot admission state. Separates the sample math from the
 * actual full-queue -> next successful admission transition so this edge
 * behavior can be native-tested without linking the Switch audio service.
 * State is only used behind both selftest and resume-ramp compile flags. */
typedef struct {
    bool pending;
    uint32_t applied;
} DinoPcmResumeRampState;

void dino_pcm_resume_ramp_reset(DinoPcmResumeRampState *state);
void dino_pcm_resume_ramp_note_full_skip(DinoPcmResumeRampState *state);
/* Returns true only when a pending one-shot was actually applied.
 * Invalid sample arguments do not clear the pending flag or modify data. */
bool dino_pcm_resume_ramp_before_submit(DinoPcmResumeRampState *state,
                                        int16_t *stereo, size_t frames,
                                        size_t attack_frames);
#endif

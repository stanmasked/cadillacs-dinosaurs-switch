#ifndef DINO_PCM_RESUME_GUARDED_INCLUDED_H
#define DINO_PCM_RESUME_GUARDED_INCLUDED_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* ROM-free EXPERIMENT ONLY. Sample-difference screening does NOT prove
 * that an audio buffer was heard on hardware or that a click was removed.
 *
 * The caller supplies the final stereo sample of the PREVIOUSLY SUBMITTED
 * PCM block. This is NOT known to be the most recently PLAYED sample in
 * an asynchronous libnx audout queue. Consequently the decision is a
 * controlled mathematical proxy and MUST NOT be enabled in production.
 */

/* Pure function: never mutates PCM. Compare the largest successive
 * absolute 16-bit sample jump, over the boundary and all attack frames.
 * Accept a fixed linear attack only if BOTH channels are non-worsening
 * and the overall worst channel improves strictly.
 *
 * NULL/invalid input => false. An unknown previous submitted frame
 * is represented by NULL and also => false, not a guessed silence.
 */
bool dino_pcm_resume_guarded_proxy_would_help(
    const int16_t previous_submitted_stereo[2],
    const int16_t *next_interleaved_stereo,
    size_t frames,
    size_t attack_frames);
#endif

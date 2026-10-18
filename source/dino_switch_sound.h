#ifndef DINO_SWITCH_SOUND_INCLUDED_H
#define DINO_SWITCH_SOUND_INCLUDED_H
#include <stdbool.h>
#include <stdint.h>

/* Optional libnx audout adapter. Device errors degrade to silent gameplay;
 * the portable 60 Hz simulation must never wait for audio hardware.
 */
bool dino_switch_sound_open(void);
void dino_switch_sound_step(uint32_t events);
void dino_switch_sound_close(void);
/* The checksum covers every generated 48kHz PCM tick before queueing.
 * It does NOT show that emulator/console speakers actually played it. */
uint64_t dino_switch_sound_pcm_witness(void);
uint32_t dino_switch_sound_pcm_ticks(void);

/* Read-only on-device diagnostics, not a measurement of actual latency.
 * They intentionally contain no audio PCM, private file paths or ROM data. */
typedef struct {
    uint32_t simulated_ticks;
    uint32_t audio_errors;
    uint32_t pending;
    uint32_t submitted;
    uint32_t released;
    uint32_t skipped;
    uint8_t active;
    uint8_t queue_valid;
    /* Queue admission reasons, not measured audio output. */
    uint32_t full_queue_skips;
    uint32_t inactive_backend_skips;
    uint32_t unexpected_slot_skips;
    uint32_t max_consecutive_skips;
} DinoSoundDiagnostics;
void dino_switch_sound_diagnostics(DinoSoundDiagnostics *out);
#endif

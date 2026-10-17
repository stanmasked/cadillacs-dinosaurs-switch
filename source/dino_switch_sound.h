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
#endif

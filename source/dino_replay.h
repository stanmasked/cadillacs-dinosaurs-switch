#ifndef DINO_REPLAY_INCLUDED_H
#define DINO_REPLAY_INCLUDED_H
#include <stdbool.h>
#include <stdint.h>

/* Original, asset-free 180-step demo. Identical controls can be consumed
 * by native C host preview and the actual Switch NRO at 60 simulation Hz.
 * This does NOT reproduce MAME/Capcom controls or game scripting.
 */
#define DINO_REPLAY_TICKS 180u
bool dino_replay_input(uint32_t tick,uint32_t *held,uint32_t *pressed);
#endif

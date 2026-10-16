#ifndef CPS1_TILE_H
#define CPS1_TILE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CPS1_GFX_BYTES 0x400000u
#define CPS1_TILE16_BYTES 128u
#define CPS1_TILE16_PIXELS 256u
#define CPS1_TILE16_COUNT (CPS1_GFX_BYTES / CPS1_TILE16_BYTES)

/* Decode one 16x16 4bpp planar CPS-1 tile from an already interleaved ROM
 * region. Returns false on null pointers or a truncated/out-of-range code.
 * Output entries are raw palette indices 0..15, never invented RGB colors.
 */
bool cps1_decode_tile16(const uint8_t *gfx, size_t gfx_size,
                        size_t code, uint8_t out[CPS1_TILE16_PIXELS]);


#define CPS1_TILE8_PIXELS 64u
#define CPS1_TILE32_PIXELS 1024u

/* CPS-1 ROM: 8x8 left/right (64 bytes shared by the two alternatives),
 * 16x16 (128 bytes) or 32x32 (512 bytes). Never returns RGB or uses
 * runtime RAM/palette. Output unchanged when validation fails.
 */
bool cps1_read_tile_pen(const uint8_t *gfx, size_t gfx_size,
                        unsigned side, size_t code, bool right_half,
                        unsigned x, unsigned y, uint8_t *pen_out);
bool cps1_decode_tile8(const uint8_t *gfx, size_t gfx_size,
                       size_t code, bool right_half,
                       uint8_t out[CPS1_TILE8_PIXELS]);
bool cps1_decode_tile32(const uint8_t *gfx, size_t gfx_size,
                        size_t code, uint8_t out[CPS1_TILE32_PIXELS]);

#endif

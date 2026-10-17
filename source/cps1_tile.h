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

/* Shared CPS-1 planar pixel reader for all three scrolling tile sizes.
 * side=8 uses the tilemap index bit 5 to select the left/right half-row;
 * side=16 and 32 ignore tile_index. Only valid mapped ROM tile codes.
 * Returns false for invalid inputs without modifying *out_pen.
 */
bool cps1_tile_pixel(const uint8_t *gfx, size_t gfx_size,
                     unsigned side, size_t code, unsigned tile_index,
                     unsigned x, unsigned y, uint8_t *out_pen);

/* Convenience decoders for 8x8 and 32x32 tilemap tiles, using the same
 * shared pixel path used by the native scrolling scene renderer.
 */
bool cps1_decode_tile8(const uint8_t *gfx, size_t gfx_size,
                       size_t code, unsigned tile_index, uint8_t out[64]);
bool cps1_decode_tile32(const uint8_t *gfx, size_t gfx_size,
                        size_t code, uint8_t out[1024]);

#endif

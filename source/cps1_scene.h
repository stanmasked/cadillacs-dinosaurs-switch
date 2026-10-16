#ifndef CPS1_SCENE_INCLUDED_H
#define CPS1_SCENE_INCLUDED_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CPS1_SCENE_W 384u
#define CPS1_SCENE_H 224u
#define CPS1_SCENE_RGBA_BYTES (CPS1_SCENE_W * CPS1_SCENE_H * 4u)
#define CPS1_SCENE_SCROLL_WORDS 8192u
#define CPS1_SCENE_OBJ_WORDS 1024u
#define CPS1_SCENE_ROW_WORDS 1024u
#define CPS1_SCENE_PALETTE_COLORS 3072u
#define CPS1_SCENE_PAYLOAD_BYTES 62494u
#define CPS1_SCENE_FILE_BYTES (16u + CPS1_SCENE_PAYLOAD_BYTES)

/* This is a ROM-free, one-frame CPS-1 memory capture, not a save-state.
 * All numbers in the serialized file are little endian; RGB channels
 * are straight 8-bit and were captured from EFFECTIVE palette RAM.
 */
typedef struct {
    uint16_t layer_control;
    uint16_t video_control;
    uint16_t scrollx[3];
    uint16_t scrolly[3];
    uint8_t enabled[3];
    uint16_t priority[4];
    uint16_t rowscroll_offset;
    uint8_t palette[CPS1_SCENE_PALETTE_COLORS][3];
    uint16_t scroll[3][CPS1_SCENE_SCROLL_WORDS];
    uint16_t obj[CPS1_SCENE_OBJ_WORDS]; /* VBlank latched */
    uint16_t rowscroll[CPS1_SCENE_ROW_WORDS];
} Cps1Scene;

/* Validates file size, version magic, payload size, reserved field and
 * CRC32. Does not write into out when file validation fails.
 */
bool cps1_scene_decode(const uint8_t *blob, size_t length, Cps1Scene *out);

/* Assemble partial CPS-1 scene with 8x8, 16x16, 32x32 tilemaps, line
 * scrolling, sprite blocks and QS2 priority masks into opaque RGBA bytes.
 * Requires interleaved 4 MiB CPS-1 gfx region. Supports global 180-degree
 * flip (VIDEO_CONTROL bit15) of the visible window. No stars, raster events,
 * or exact priority-mask edge-case guarantees yet.
 */
bool cps1_scene_render(const uint8_t *gfx, size_t gfx_bytes,
                       const Cps1Scene *scene, uint8_t *rgba, size_t rgba_bytes);


/* Move the diagnostic view across all three background layers.
 * Original sprite screen coordinates remain unchanged. This is a manual
 * viewer pan only, NOT emulated game/camera logic. Arithmetic wraps at
 * 16 bits like CPS-A scroll register writes. Returns false for no-op.
 */
bool cps1_scene_pan(Cps1Scene *scene, int dx, int dy);

#endif

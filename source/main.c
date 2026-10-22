/* Cadillacs and Dinosaurs / CPS-1 World 930201
 * Native ROM-free diagnostic tile viewer. NOT an arcade emulator or a game.
 *
 * Expects locally assembled, user-owned graphics region at
 * sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin (exactly 0x400000 bytes).
 */
#include <switch.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cps1_tile.h"
#include "cps1_scene.h"
#include "cps1_sequence.h"
#include "dino_arena.h"
#include "dino_replay.h"
#include "dino_replay_witness.h"
#include "dino_switch_sound.h"
#ifdef DINO_EMULATOR_SELFTEST
#include "dino_guest_ack_trace.h"
#include "dino_guest_frame_clock.h"
#include "dino_guest_counter_probe.h"
#include "dino_sfx.h"
#include "dino_pcm_witness.h"
#endif

enum { FB_WIDTH = 1280, FB_HEIGHT = 720, TILE_SCALE = 4,
       GRID_COLS = 16, GRID_ROWS = 8, PAGE_TILES = GRID_COLS * GRID_ROWS,
       PAGE_COUNT = CPS1_TILE16_COUNT / PAGE_TILES };
static const char *const GFX_PATH =
    "sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin";
static uint8_t s_cache[PAGE_TILES][CPS1_TILE16_PIXELS];
static const char *const SCENE_PATH =
    "sdmc:/switch/cadillacs-dinosaurs-switch/scene.bin";
static const char *const SEQUENCE_PATH =
    "sdmc:/switch/cadillacs-dinosaurs-switch/sequence.bin";

#ifdef DINO_SYNTHETIC_SCENE_GUEST_PROBE
/* Opt-in evidence only. FNV over synthetic RGBA and guest framebuffer
 * samples is computed in the genuine libnx NRO, not a host replay.
 * Never enable in normal release or the separate training-room selftest. */
static uint64_t synthetic_fnv64(const uint8_t *p,size_t count) {
    uint64_t hash=UINT64_C(14695981039346656037);
    for (size_t i=0;i<count;++i) {
        hash ^= p[i];
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}
static uint64_t synthetic_display_sample(const uint32_t *pixels,unsigned pitch) {
    uint64_t hash=UINT64_C(14695981039346656037);
    for (unsigned y=0;y<CPS1_SCENE_H;y+=13u)
        for (unsigned x=0;x<CPS1_SCENE_W;x+=13u) {
            /* Always sample inside the native 3x CPS1 scene viewport. */
            uint32_t rgba=pixels[(24u+3u*y)*pitch+(64u+3u*x)];
            for (unsigned b=0;b<4u;++b) {
                hash^=(uint8_t)(rgba>>(b*8u));
                hash*=UINT64_C(1099511628211);
            }
        }
    return hash;
}
#endif

/* A tiny self-contained bitmap font. Only HUD ASCII is required. */
typedef struct { char letter; uint8_t rows[7]; } Glyph;
static const Glyph s_font[] = {
    {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
    {'C',{15,16,16,16,16,16,15}}, {'D',{30,17,17,17,17,17,30}},
    {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
    {'G',{15,16,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
    {'I',{31,4,4,4,4,4,31}}, {'J',{7,2,2,2,18,18,12}},
    {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
    {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
    {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
    {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
    {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
    {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
    {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
    {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
    {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
    {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
    {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,30,1,1,17,14}},
    {'6',{6,8,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
    {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,2,12}},
    {'-',{0,0,0,31,0,0,0}}, {'/',{1,1,2,4,8,16,16}},
    {':',{0,4,4,0,4,4,0}}, {' ',{0,0,0,0,0,0,0}},
    {'+', {0,4,4,31,4,4,0}},
};

static uint32_t rgb(unsigned r, unsigned g, unsigned b) {
    return RGBA8_MAXALPHA(r,g,b);
}

static void rectangle(uint32_t *frame, unsigned pitch, int x, int y,
                      int width, int height, uint32_t color) {
    int x2 = x + width;
    int y2 = y + height;
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    if (x2 > FB_WIDTH) x2 = FB_WIDTH;
    if (y2 > FB_HEIGHT) y2 = FB_HEIGHT;
    for (int py = y; py < y2; ++py) {
        for (int px = x; px < x2; ++px) frame[py * pitch + px] = color;
    }
}

static const uint8_t *glyph_for(char ch) {
    for (size_t i=0; i<sizeof(s_font)/sizeof(s_font[0]); ++i)
        if (s_font[i].letter == ch) return s_font[i].rows;
    return NULL;
}

static void label(uint32_t *frame, unsigned pitch, int x, int y,
                  const char *string, unsigned size, uint32_t color) {
    for (const char *p = string; *p; ++p, x += 6 * (int)size) {
        const uint8_t *rows = glyph_for(*p);
        if (!rows) continue;
        for (int cy=0; cy<7; ++cy)
            for (int cx=0; cx<5; ++cx)
                if (rows[cy] & (1u << (4-cx)))
                    rectangle(frame,pitch,x+cx*(int)size,y+cy*(int)size,
                              (int)size,(int)size,color);
    }
}

static uint8_t *load_region(void) {
    FILE *file=fopen(GFX_PATH,"rb");
    if (!file) return NULL;
    uint8_t *gfx=malloc(CPS1_GFX_BYTES);
    if (!gfx) { fclose(file); return NULL; }
    size_t read_bytes=fread(gfx,1,CPS1_GFX_BYTES,file);
    int trailing=fgetc(file);
    fclose(file);
    if (read_bytes != CPS1_GFX_BYTES || trailing != EOF) {
        free(gfx);
        return NULL;
    }
    return gfx;
}

static bool cache_page(const uint8_t *gfx, unsigned page) {
    if (page >= PAGE_COUNT) return false;
    for (size_t tile=0; tile<PAGE_TILES; ++tile)
        if (!cps1_decode_tile16(gfx,CPS1_GFX_BYTES,
                                page*PAGE_TILES+tile,s_cache[tile]))
            return false;
    return true;
}

static void viewer_frame(uint32_t *frame, unsigned pitch, unsigned page,
                         bool invert, bool grid, bool transparent) {
    rectangle(frame,pitch,0,0,FB_WIDTH,FB_HEIGHT,rgb(10,16,25));
    label(frame,pitch,40,19,"CADILLACS AND DINOSAURS",3,rgb(224,227,224));
    label(frame,pitch,40,54,"CPS1 WORLD 930201  -  16X16 TILE INSPECTOR",2,rgb(160,195,210));
    char info[85];
    snprintf(info,sizeof(info),"PAGE %03u / %03u  CODES %05u - %05u",
             page+1, PAGE_COUNT,page*PAGE_TILES,page*PAGE_TILES+PAGE_TILES-1);
    label(frame,pitch,128,82,info,2,rgb(248,180,104));
    rectangle(frame,pitch,124,108,1032,520,rgb(33,45,55));
    for (unsigned i=0; i<PAGE_TILES; ++i) {
        int ox=128+(int)(i%GRID_COLS)*64;
        int oy=112+(int)(i/GRID_COLS)*64;
        for (int y=0; y<16; ++y) {
            for (int x=0; x<16; ++x) {
                uint8_t pen=s_cache[i][y*16+x];
                uint8_t shade;
                if (transparent && pen==15)
                    shade=((x/4+y/4)&1)? 44:66;
                else
                    shade=invert ? (uint8_t)(255-pen*17) : (uint8_t)(pen*17);
                uint32_t color=rgb(shade,shade,shade);
                rectangle(frame,pitch,ox+x*TILE_SCALE,oy+y*TILE_SCALE,
                          TILE_SCALE,TILE_SCALE,color);
            }
        }
        if (grid) {
            rectangle(frame,pitch,ox,oy,64,1,rgb(82,110,126));
            rectangle(frame,pitch,ox,oy,1,64,rgb(82,110,126));
        }
    }
    label(frame,pitch,40,643,"LEFT RIGHT PAGE   UP DOWN 16   L R 8   A INVERT",2,rgb(205,214,221));
    label(frame,pitch,40,669,"B TRANSPARENT  Y GRID  PLUS EXIT",2,rgb(205,214,221));
    label(frame,pitch,955,682,"ROM-FREE NRO",2,rgb(113,149,169));
    label(frame,pitch,40,696,"X SCENE  IF CAPTURE AVAILABLE",1,rgb(150,182,192));
}

static uint8_t *load_scene_image(const uint8_t *gfx, Cps1Scene **scene_out) {
    if (!scene_out) return NULL;
    *scene_out = NULL;
    FILE *file = fopen(SCENE_PATH,"rb");
    if (!file) return NULL;
    uint8_t *packed=malloc(CPS1_SCENE_FILE_BYTES);
    Cps1Scene *scene=malloc(sizeof(*scene));
    uint8_t *rgba=malloc(CPS1_SCENE_RGBA_BYTES);
    if (!packed || !scene || !rgba) {
        free(packed); free(scene); free(rgba);
        fclose(file);
        return NULL;
    }
    size_t count=fread(packed,1,CPS1_SCENE_FILE_BYTES,file);
    int trailing=fgetc(file);
    fclose(file);
    bool valid = (count==CPS1_SCENE_FILE_BYTES && trailing==EOF &&
                  cps1_scene_decode(packed,count,scene) &&
                  cps1_scene_render(gfx,CPS1_GFX_BYTES,scene,
                                    rgba,CPS1_SCENE_RGBA_BYTES));
    free(packed);
    if (!valid) { free(scene); free(rgba); return NULL; }
    *scene_out = scene; /* keep decoded mutable scene for camera pan */
    return rgba;
}

static void scene_frame(uint32_t *frame,unsigned pitch,const uint8_t *rgba,
                        const Cps1Sequence *sequence,
                        const Cps1Playback *playback) {
    rectangle(frame,pitch,0,0,FB_WIDTH,FB_HEIGHT,rgb(9,14,22));
    for (unsigned y=0; y<CPS1_SCENE_H; ++y) {
        for (unsigned x=0; x<CPS1_SCENE_W; ++x) {
            const uint8_t *c=rgba+4u*(y*CPS1_SCENE_W+x);
            uint32_t color=rgb(c[0],c[1],c[2]);
            unsigned dx=64u+x*3u,dy=24u+y*3u;
            for (unsigned sy=0;sy<3;++sy)
                for (unsigned sx=0;sx<3;++sx)
                    frame[(dy+sy)*pitch+dx+sx]=color;
        }
    }
    if (sequence && playback) {
        char status[96];
        const char *speed=playback->speed_num==1?"HALF":
                          playback->speed_num==4?"DOUBLE":"NORMAL";
        snprintf(status,sizeof(status),"FRAME %03u / %03u  FPS %02u  %s  %s",
                 playback->index+1,sequence->frame_count,sequence->fps,
                 speed,playback->paused?"PAUSED":"PLAYING");
        label(frame,pitch,64,4,status,1,rgb(215,226,231));
        label(frame,pitch,64,704,
              "A PAUSE  B NEXT  Y PREV  L R SPEED  X TILES",1,rgb(180,198,206));
    } else {
        label(frame,pitch,64,4,"NATIVE CPS1 SCENE   DPAD PAN   ZR FAST   A RESET",1,rgb(215,226,231));
        label(frame,pitch,64,704,"X TILES   PLUS EXIT   DIAGNOSTIC NOT GAMEPLAY",1,rgb(180,198,206));
    }
}

/* Load every versioned frame into bounded RAM. Keep the sequence buffer
 * alive as long as Cps1Sequence points inside it. Prefer sequence.bin if
 * present; fall back to the legacy standalone scene.bin otherwise. */
static uint8_t *load_sequence_image(const uint8_t *gfx,
                                    Cps1Scene **scene_out,
                                    Cps1Sequence *sequence_out,
                                    uint8_t **buffer_out) {
    if (!scene_out || !sequence_out || !buffer_out) return NULL;
    *buffer_out=NULL;
    FILE *file=fopen(SEQUENCE_PATH,"rb");
    if (!file) return NULL;
    if (fseek(file,0,SEEK_END)!=0) { fclose(file);return NULL; }
    long length=ftell(file);
    if (length < (long)(CPS1_SEQUENCE_HEADER_BYTES+CPS1_SCENE_FILE_BYTES) ||
        (unsigned long)length>CPS1_SEQUENCE_MAX_BYTES ||
        fseek(file,0,SEEK_SET)!=0) { fclose(file);return NULL; }
    uint8_t *blob=malloc((size_t)length);
    Cps1Scene *scene=malloc(sizeof(*scene));
    uint8_t *rgba=malloc(CPS1_SCENE_RGBA_BYTES);
    if (!blob || !scene || !rgba) {
        free(blob);free(scene);free(rgba);
        fclose(file);return NULL;
    }
    bool ok=fread(blob,1,(size_t)length,file)==(size_t)length;
    fclose(file);
    Cps1Sequence seq={0};
    if (ok) ok=cps1_sequence_decode(blob,(size_t)length,&seq);
    if (ok) ok=cps1_sequence_frame(&seq,0,scene);
    if (ok) ok=cps1_scene_render(gfx,CPS1_GFX_BYTES,scene,rgba,CPS1_SCENE_RGBA_BYTES);
    if (!ok) {
        free(blob);free(scene);free(rgba);
        return NULL;
    }
    *sequence_out=seq;
    *scene_out=scene;
    *buffer_out=blob;
    return rgba;
}

/* Fully ROM-free geometry preview: intentionally not original game art.
 * Placeholder actor and stationary dummy use independently written rules.
 */
static const char *arena_pose_name(DinoArenaPose pose) {
    switch (pose) {
        case DINO_POSE_IDLE: return "IDLE";
        case DINO_POSE_WALK: return "WALK";
        case DINO_POSE_JUMP: return "JUMP";
        case DINO_POSE_ATTACK: return "ATTACK";
        case DINO_POSE_HURT: return "HURT";
        case DINO_POSE_KO: return "KO";
        case DINO_POSE_WINDUP: return "WINDUP";
        default: return "UNKNOWN";
    }
}

static void arena_frame(uint32_t *frame, unsigned pitch,
                        const DinoArena *arena, bool have_gfx,
                        uint32_t demo_ticks, bool demo_active,
                        bool demo_complete, uint64_t demo_witness,
                        uint8_t counter_feedback_ticks) {
    const DinoArenaPose player=dino_arena_player_pose(arena);
    const DinoArenaPose enemy=dino_arena_dummy_pose(arena);
    const unsigned phase=dino_arena_pose_phase(arena);
    rectangle(frame,pitch,0,0,FB_WIDTH,FB_HEIGHT,rgb(11,18,29));
    /* Fully ROM-free placeholder sprites in original 384x224 coordinates.
     * Visual poses derive solely from the 60Hz deterministic simulation. */
    const int ox=64, oy=24, scale=3;
    rectangle(frame,pitch,ox,oy,1152,672,rgb(30,61,70));
    rectangle(frame,pitch,ox,oy+240,1152,432,rgb(62,83,74));
    for (int lane=0;lane<7;++lane)
        rectangle(frame,pitch,ox,oy+240+lane*64,1152,1,rgb(86,108,94));
    rectangle(frame,pitch,0,0,1280,72,rgb(11,18,29));
    label(frame,pitch,52,19,"TRAINING ROOM  -  ORIGINAL ROM FREE PROTOTYPE",
          2,rgb(226,233,229));
    label(frame,pitch,52,55,
          "PLACEHOLDER ACTOR AND DUMMY  -  NOT ORIGINAL GAMEPLAY",
          1,rgb(160,190,207));

    const int x=ox+arena->dummy_x*scale;
    const int y=oy+arena->dummy_y*scale;
    if (arena->dummy_impact_flash) {
        /* Short impact marker persists for six simulated ticks and
         * is independent of renderer timing or protected game graphics. */
        rectangle(frame,pitch,x-25,y-128,50,5,rgb(255,243,164));
        rectangle(frame,pitch,x-3,y-146,6,40,rgb(255,243,164));
    }
    if (arena->finisher_flash) {
        /* A short invented highlight after a three-hit knockback.
         * The visual effect is driven by the fixed 60 Hz combat state. */
        rectangle(frame,pitch,x-34,y-148,68,7,rgb(251,221,89));
        rectangle(frame,pitch,x-29,y-138,58,4,rgb(241,162,73));
    }
    if (enemy==DINO_POSE_KO) {
        rectangle(frame,pitch,x-29,y-14,58,12,rgb(101,81,66));
    } else {
        const int walk_bob=enemy==DINO_POSE_WALK && phase ? 5 : 0;
        const int crouch=enemy==DINO_POSE_WINDUP ? 9 : 0;
        rectangle(frame,pitch,x-17,y-7,34,8,rgb(26,37,40));
        rectangle(frame,pitch,x-16,y-102+walk_bob+crouch,32,
                  94-crouch-walk_bob,
                  enemy==DINO_POSE_HURT ? rgb(247,196,120):
                  enemy==DINO_POSE_WINDUP ? rgb(224,149,65):
                                           rgb(190,126,74));
        if (enemy==DINO_POSE_WINDUP) {
            rectangle(frame,pitch,x-20,y-112,4,110,rgb(254,224,69));
            rectangle(frame,pitch,x+16,y-112,4,110,rgb(254,224,69));
        }
        if (enemy==DINO_POSE_ATTACK) {
            const int ax=x+(arena->dummy_facing_right?17:-77);
            rectangle(frame,pitch,ax,y-70,60,18,rgb(246,142,94));
        }
        rectangle(frame,pitch,x-12,y-113+walk_bob+crouch,24,16,
                  rgb(231,202,142));
        for (unsigned i=0;i<arena->dummy_hp;++i)
            rectangle(frame,pitch,x-24+(int)i*17,y-133,12,6,
                      rgb(250,196,87));
    }

    const int px=ox+arena->x*scale;
    const int py=oy+arena->y*scale;
    const int rise=arena->z*scale;
    if (arena->player_impact_flash) {
        rectangle(frame,pitch,px-25,py-rise-114,50,5,rgb(255,165,105));
        rectangle(frame,pitch,px-3,py-rise-132,6,40,rgb(255,165,105));
    }
    rectangle(frame,pitch,px-16,py-7,32,7,rgb(27,39,43));
    if (player==DINO_POSE_KO) {
        rectangle(frame,pitch,px-34,py-15,68,12,rgb(91,112,140));
        rectangle(frame,pitch,px+(arena->facing_right?17:-34),
                  py-18,17,17,rgb(231,218,164));
    } else {
        const int bob=(player==DINO_POSE_WALK && phase)?5:0;
        uint32_t body=player==DINO_POSE_HURT ? rgb(251,121,106):
                      arena->player_invuln ? rgb(111,136,184):
                      player==DINO_POSE_ATTACK ? rgb(86,210,207):
                                                 rgb(62,180,208);
        rectangle(frame,pitch,px-16,py-rise-74+bob,32,67-bob,body);
        rectangle(frame,pitch,px-12,py-rise-92+bob,24,18,
                  rgb(231,218,164));
        rectangle(frame,pitch,px+(arena->facing_right?9:-15),
                  py-rise-63+bob,6,13,rgb(238,233,210));
        if (player==DINO_POSE_WALK)
            rectangle(frame,pitch,px+(phase?7:-12),py-rise-9,
                      9,8,rgb(237,238,216));
        if (player==DINO_POSE_ATTACK) {
            const int hit_x=px+(arena->facing_right?16:-75);
            rectangle(frame,pitch,hit_x,py-rise-63,60,18,
                      rgb(249,214,100));
        }
    }

    /* Technical on-console diagnostics, not actual measured latency:
     * these are logical blocks submitted, acknowledged or discarded. */
    DinoSoundDiagnostics audio;
    dino_switch_sound_diagnostics(&audio);
    /* Keep the original lower depth lane visible instead of covering
     * the player's feet with an enlarged bottom-HUD overlay. */
    rectangle(frame,pitch,0,74,1280,23,rgb(11,18,29));
    rectangle(frame,pitch,0,661,1280,59,rgb(11,18,29));
    char audio_line[155];
    snprintf(audio_line,sizeof(audio_line),
             "AUDIO %s  QUEUED %u/2  SENT %u  RELEASED %u  SKIPPED %u  ERRORS %u",
             !audio.queue_valid?"INVALID":audio.active?"ON":"OFF",
             (unsigned)audio.pending,(unsigned)audio.submitted,
             (unsigned)audio.released,(unsigned)audio.skipped,
             (unsigned)audio.audio_errors);
    label(frame,pitch,52,82,audio_line,1,
          audio.active && audio.queue_valid?rgb(145,224,166):
                                              rgb(251,190,130));
    if (demo_active || demo_complete) {
        char demo_line[86];
        snprintf(demo_line,sizeof(demo_line),
                 "C REPLAY %03u/180  %s  HP %u  HITS %u",
                 (unsigned)demo_ticks,
                 demo_complete?"DONE - Y RESET":"PLAYING",
                 (unsigned)arena->player_hp,
                 (unsigned)arena->successful_hits);
        label(frame,pitch,52,110,demo_line,1,rgb(248,215,119));
        char witness_line[55];
        snprintf(witness_line,sizeof(witness_line),
                 "STATE FNV64 %016llX",
                 (unsigned long long)demo_witness);
        label(frame,pitch,52,128,witness_line,1,rgb(249,220,148));
        /* Independent witness for C-generated audio samples; this does
         * NOT prove actual audout delivery, speakers or emulator sound. */
        char pcm_line[75];
        snprintf(pcm_line,sizeof(pcm_line),
                 "PCM FNV64 %016llX  BLOCKS %03u",
                 (unsigned long long)dino_switch_sound_pcm_witness(),
                 (unsigned)dino_switch_sound_pcm_ticks());
        label(frame,pitch,52,146,pcm_line,1,rgb(162,222,231));
    }
    char status[140];
    snprintf(status,sizeof(status),
             "PLAYER %s HP %u  ENEMY %s HP %u  COMBO %u/3  HITS %03u  %s",
             arena_pose_name(player),(unsigned)arena->player_hp,
             arena_pose_name(enemy),(unsigned)arena->dummy_hp,
             (unsigned)arena->combo_hits,
             (unsigned)arena->successful_hits,
             arena->sparring?"SPAR ON":"SPAR OFF");
    label(frame,pitch,52,670,status,1,rgb(218,228,224));
    /* A successful counter remains legible for six simulated ticks,
     * even when multiple game ticks precede one framebuffer refresh.
     * The legacy replay never emits this event and remains identical. */
    if (counter_feedback_ticks)
        label(frame,pitch,800,670,"COUNTER!",1,rgb(91,235,201));
    label(frame,pitch,52,698,
          "DPAD MOVE  A HIT  B JUMP  X SPAR  Y RESET  - DEMO  + EXIT",
          1,rgb(182,207,219));
    if (have_gfx)
        label(frame,pitch,755,698,"ZL TILE AND SCENE VIEW",1,
              rgb(169,210,182));
}

#ifdef DINO_EMULATOR_SELFTEST
/* Stage 253: diagnostic-only 16-bit render-iteration watermark.
 * The 16 cells live in the unused bottom HUD of the ROM-free arena,
 * never in protected game art or in release builds. */
enum { DINO_TOKEN_SLOTS=16, DINO_TOKEN_TRACE_CAP=64 };
typedef struct {
    uint32_t render_iteration,arena_tick,feedback_ttl,impact_ttl;
    uint16_t token;
} DinoCounterTokenFrame;
static void dino_counter_token_draw(uint32_t *frame,unsigned pitch,
                                     uint16_t token) {
    rectangle(frame,pitch,925,686,9,9,rgb(255,0,153));
    rectangle(frame,pitch,1165,686,9,9,rgb(0,255,204));
    for (unsigned bit=0;bit<DINO_TOKEN_SLOTS;++bit)
        rectangle(frame,pitch,942+(int)bit*12,686,9,9,
                  (token&(1u<<bit))?rgb(250,250,250):rgb(15,35,50));
}
static bool dino_counter_token_check(const uint32_t *frame,
                                     unsigned pitch,uint16_t token) {
    if (frame[690u*pitch+929u]!=rgb(255,0,153) ||
        frame[690u*pitch+1169u]!=rgb(0,255,204)) return false;
    for (unsigned bit=0;bit<DINO_TOKEN_SLOTS;++bit)
        if (frame[690u*pitch+946u+12u*bit] !=
            ((token&(1u<<bit))?rgb(250,250,250):rgb(15,35,50)))
            return false;
    return true;
}
#endif

static void fallback_text(PadState *pad) {
    consoleInit(NULL);
    printf("Cadillacs and Dinosaurs - CPS-1 tile viewer\n\n");
    printf("No valid local graphics region found.\n\n");
    printf("Expected EXACTLY 4,194,304 bytes at:\n");
    printf("%s\n\n", GFX_PATH);
    printf("On a computer, create gfx.bin from your own dino.zip:\n");
    printf("python3 tools/cps1_gfx.py dino.zip --out-local gfx.bin\n\n");
    printf("Place gfx.bin on your Switch SD card.\n");
    printf("No ROM files are included with this homebrew.\n\n");
    printf("Press PLUS to exit.\n");
    while (appletMainLoop()) {
        padUpdate(pad);
        if (padGetButtonsDown(pad) & HidNpadButton_Plus) break;
        consoleUpdate(NULL);
    }
    consoleExit(NULL);
}


#ifdef DINO_EMULATOR_SELFTEST
/* Real ARM64 guest-only telemetry: PCM synthesis, libnx queue admission
 * and actual speaker playback must remain three distinct claims.
 * This is excluded from the normal player-facing homebrew build. */
/* 900 simulated ticks (15 seconds at target 60 Hz) AFTER real guest
 * controller actions. Never infer emulator wall-time or audibility. */
enum { DINO_GUEST_AUDIO_STRESS_TICKS=900,
       DINO_GUEST_AUDIO_STRESS_PERIOD=150 };
typedef struct {
    uint32_t single_ticks, batched_ticks;
    uint32_t single_skips, batched_skips;
    uint32_t batched_frames, largest_batch;
    uint32_t first_ticks, later_ticks, first_skips, later_skips;
    uint32_t first_full, first_recovered, later_full, later_recovered;
    /* Actual released PCM pages at each guest simulation tick. */
    uint32_t single_releases, first_releases, later_releases;
    uint32_t previous_released;
    uint32_t previous_full, previous_recovered;
    uint32_t previous_skips, previous_frame_id;
    uint32_t previous_submitted, previous_mid_calls;
    uint32_t previous_mid_releases;
} DinoGuestBatchStats;
/* Fixed 900x13 counters (46.8 KiB), allocated only in a selftest NRO.
 * No filesystem I/O while collecting measurements inside game ticks. */
static DinoGuestAckTrace s_guest_ack_tick_trace;
/* Selftest-only 4096 x 16-byte capped interval ledger. */
static DinoGuestFrameClock s_guest_frame_clock;
static void guest_audio_stress_row(FILE *stream, const char *event,
                                   uint32_t elapsed, const DinoArena *arena,
                                   const DinoGuestBatchStats *batch) {
    DinoSoundDiagnostics stats;
    dino_switch_sound_diagnostics(&stats);
    fprintf(stream,
            "%s,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%016llX,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
            event,(unsigned)elapsed,(unsigned)arena->ticks,
            (unsigned)stats.simulated_ticks,
            (unsigned)dino_switch_sound_pcm_ticks(),
            (unsigned)stats.active,(unsigned)stats.queue_valid,
            (unsigned)stats.pending,(unsigned)stats.submitted,
            (unsigned)stats.released,(unsigned)stats.skipped,
            (unsigned)stats.audio_errors,
            (unsigned long long)dino_switch_sound_pcm_witness(),
            (unsigned)stats.full_queue_skips,
            (unsigned)stats.inactive_backend_skips,
            (unsigned)stats.unexpected_slot_skips,
            (unsigned)stats.max_consecutive_skips,
            (unsigned)batch->single_ticks,
            (unsigned)batch->batched_ticks,
            (unsigned)batch->single_skips,
            (unsigned)batch->batched_skips,
            (unsigned)batch->batched_frames,
            (unsigned)batch->largest_batch,
            (unsigned)stats.pre_poll_full_steps,
            (unsigned)stats.pre_poll_recovered_steps,
            (unsigned)batch->first_ticks,
            (unsigned)batch->later_ticks,
            (unsigned)batch->first_skips,
            (unsigned)batch->later_skips,
            (unsigned)batch->first_full,
            (unsigned)batch->first_recovered,
            (unsigned)batch->later_full,
            (unsigned)batch->later_recovered,
            (unsigned)batch->single_releases,
            (unsigned)batch->first_releases,
            (unsigned)batch->later_releases,
            (unsigned)dino_switch_sound_guest_mid_batch_enabled(),
            (unsigned)dino_switch_sound_guest_mid_batch_calls(),
            (unsigned)dino_switch_sound_guest_mid_batch_releases());
    fflush(stream);
}

static void guest_report_row(FILE *stream, const char *event,
                             uint32_t ticks, const DinoArena *arena,
                             uint64_t state_witness) {
    DinoSoundDiagnostics audio;
    dino_switch_sound_diagnostics(&audio);
    fprintf(stream,
            "%s,%u,%d,%u,%u,%016llX,%016llX,%u,"
            "%u,%u,%u,%u,%u,%u,%u,%u\n",
            event,(unsigned)ticks,arena->x,
            (unsigned)arena->player_hp,
            (unsigned)arena->successful_hits,
            (unsigned long long)state_witness,
            (unsigned long long)dino_switch_sound_pcm_witness(),
            (unsigned)dino_switch_sound_pcm_ticks(),
            (unsigned)audio.simulated_ticks,
            (unsigned)audio.active,
            (unsigned)audio.queue_valid,
            (unsigned)audio.pending,
            (unsigned)audio.submitted,
            (unsigned)audio.released,
            (unsigned)audio.skipped,
            (unsigned)audio.audio_errors);
    fflush(stream);
}
#endif

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    padConfigureInput(1,HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    /* Mount sdmc BEFORE probing the optional diagnostic gfx.bin/sequence.bin.
     * The former mount only happened after load_region(), inside the
     * arena-only emulator selftest path: a cold viewer could therefore miss
     * otherwise valid SD assets. An already mounted sdmc device is also OK;
     * even on mount failure the synthetic geometry arena remains usable.
     * No ROM data is generated, captured or published by this operation.
     */
    (void)fsdevMountSdmc();
    /* Without local graphics, start a purely geometric training room.
     * With local graphics present (original owned or synthetic), the
     * established tile/scene viewer remains the initial mode and ZL
     * switches to/from the training room.
     */
    uint8_t *gfx=load_region();

    Framebuffer fb;
    Result rc=framebufferCreate(&fb,nwindowGetDefault(),FB_WIDTH,FB_HEIGHT,
                                PIXEL_FORMAT_RGBA_8888,2);
    if (R_FAILED(rc)) {
        free(gfx);
        fallback_text(&pad);
        return 1;
    }
    rc=framebufferMakeLinear(&fb);
    if (R_FAILED(rc)) {
        framebufferClose(&fb);
        free(gfx);
        fallback_text(&pad);
        return 1;
    }

    unsigned page=0;
    bool invert=false,grid=true,transparent=true;
    Cps1Scene *scene=NULL;
    Cps1Sequence sequence={0};
    Cps1Playback playback;
    cps1_playback_init(&playback);
    uint8_t *sequence_blob=NULL;
    uint8_t *scene_rgba=NULL;
    if (gfx) {
        scene_rgba=load_sequence_image(gfx,&scene,&sequence,&sequence_blob);
        if (!scene_rgba) scene_rgba=load_scene_image(gfx,&scene);
    }
    uint16_t initial_scrollx[3]={0}, initial_scrolly[3]={0};
    if (scene) {
        memcpy(initial_scrollx,scene->scrollx,sizeof(initial_scrollx));
        memcpy(initial_scrolly,scene->scrolly,sizeof(initial_scrolly));
    }
    bool show_scene=(sequence_blob!=NULL);
    bool arena_active=(gfx==NULL);
#ifdef DINO_SYNTHETIC_SCENE_GUEST_PROBE
    /* A valid scene file by itself does not establish synthetic origin.
     * Probe writes nothing unless the intentionally artificial Stage308
     * graphics signature and exactly the Stage307 14@2fps format exist.
     * Host CI independently checks each byte of both staged binaries.
     */
    const bool synthetic_scene_guest_ready =
        gfx && sequence_blob && scene_rgba && scene &&
        sequence.frame_count==14u && sequence.fps==2u &&
        memcmp(gfx,"ROM-FREE CPS1 SYNTHETIC PIXELS STAGE308",39u)==0;
    uint32_t synthetic_guest_seen=0u;
    unsigned synthetic_guest_rows=0u;
#ifdef DINO_SYNTHETIC_SCENE_HOST_VISIBLE_313
    /* Stage313 host-driven optical experiment. Freeze each submitted
     * synthetic scene until the host captures the window and acknowledges
     * the current index on the isolated NeXium SD. */
    if (synthetic_scene_guest_ready) playback.paused=true;
#endif
#endif
    DinoArena arena;
    dino_arena_reset(&arena);
    /* Keep audout completely shut down in the tile/scene viewer.
     * Only the ROM-free arena requires synthesized training audio. */
    if (arena_active) (void)dino_switch_sound_open();
    uint32_t pending_actions=0;
    uint8_t counter_feedback_ticks=0; /* presentation only, not DinoArena */
    uint32_t demo_ticks=0;
    uint64_t demo_witness=DINO_WITNESS_INIT;
    bool demo_active=false, demo_complete=false;
#ifdef DINO_EMULATOR_SELFTEST
    /* CI-only Switch guest execution witness, never enabled by default.
     * Reports invented training-room state only: no ROMs, keys, graphics,
     * commercial audio, emulator configuration or private file paths. */
    FILE *guest_witness=NULL;
    bool guest_first_frame=false, guest_done=false;
    /* CI-only physical HID witness. Unlike the replay inputs below,
     * these flags can only originate from padGetButtons*/ 
    FILE *guest_controller_witness=NULL;
    bool guest_controller_active=false, guest_controller_done=false;
    uint32_t guest_controller_flags=0;
    bool guest_counter_hid_done=false; /* stage 234, after audio stress */
    bool guest_counter_zr_edge_pending=false;
    /* Stage 244: independent 60Hz naturally advancing ROM-free AI trial.
     * NEVER edit coordinates, windup, facing or cooldown for this witness.
     * It runs after the previous prepared HID proof, without changing the
     * player-facing arena, replay ledger or measured 900-tick audio path. */
    DinoArena guest_natural_counter;
    bool guest_natural_counter_active=false;
    bool guest_natural_counter_done=false;
    bool guest_natural_ready_written=false;
    /* Stage 246: observe the *rendered* arena after real host Y/X/ZR.
     * No artificial x, enemy windup, tick countdown or attack setup.
     * This is kept separate from prior Stage 245 required evidence. */
    bool guest_live_reset_seen=false;
    bool guest_live_spar_armed=false;
    bool guest_live_ready_written=false;
    bool guest_live_counter_done=false;
    /* Stage 248: distinguish actual guest-written framebuffer pixels
     * from game-state events and from emulator host-screen visibility. */
    bool guest_counter_framebuffer_written=false;
    /* Bounded per-submitted-frame trace, not an input or host clock. */
    DinoCounterTokenFrame guest_token_rows[DINO_TOKEN_TRACE_CAP];
    unsigned guest_token_count=0u;
    bool guest_token_trace_overflow=false;
    bool guest_token_trace_written=false;
    bool guest_live_zr_edge_pending=false;
    uint32_t guest_live_spar_origin=0u;
    /* An independent, ordered game-tick trace of actual HID effects.
     * Tick values are guest simulation time, NOT host input latency. */
    FILE *guest_hid_timeline=NULL;
    uint32_t guest_hid_phase=0;
    FILE *guest_audio_stress=NULL;
    /* ROM-free selftest only. Never write a CSV in the measured tick loop. */
    bool guest_ack_tick_collecting=false;
    uint32_t guest_ack_tick_count=0;
    bool guest_frame_clock_started=false;
    bool guest_frame_clock_done=false;
    bool guest_frame_clock_flushed=false;
    uint32_t guest_audio_stress_start=0;
    uint32_t guest_audio_stress_next=DINO_GUEST_AUDIO_STRESS_PERIOD;
    bool guest_audio_stress_done=false;
#if defined(DINO_AUDIO_EXPERIMENT_RESUME_RAMP)
    /* Snapshot only, no disk writes during measured 900 game ticks. */
    uint32_t guest_resume_start_count=0,guest_resume_end_count=0;
    uint32_t guest_resume_start_full=0,guest_resume_end_full=0;
    uint32_t guest_resume_initial_pending=0,guest_resume_final_pending=0;
    bool guest_resume_report_ready=false,guest_resume_report_written=false;
#endif
    DinoGuestBatchStats guest_batch={0};
    uint32_t guest_frame_id=0;
    if (arena_active) {
        /* sdmc was already mounted before the optional gfx/sequence probe.
         * Do not attempt a second mount of the same devoptab device. */
        /* Stage 229: guest-executed, scripted ROM-free counter proof.
         * This writes only synthetic diagnostic state, before the main
         * 180-tick replay; never record raw pad values or ROM contents.
         * Its result is independently checked by a fail-closed host
         * verifier, rather than being equated with physical ZR input. */
        FILE *counter_guest=fopen("sdmc:/cadillacs-counter-guest.csv","w");
        if (counter_guest) {
            (void)dino_guest_counter_probe(counter_guest);
            (void)fclose(counter_guest);
        }
        guest_witness=fopen("sdmc:/cadillacs-arena-selftest.csv","w");
        if (guest_witness) {
            fputs("event,ticks,player_x,player_hp,hits,state_fnv64,"
                  "pcm_fnv64,pcm_blocks,audio_ticks,audio_active,"
                  "audio_queue_valid,audio_pending,audio_submitted,"
                  "audio_released,audio_skipped,audio_errors\n",guest_witness);
            guest_report_row(guest_witness,"START",0u,&arena,demo_witness);
        }
        demo_active=true;
    }
#endif
    u64 arena_clock_carry=0;
    if (gfx) cache_page(gfx,page);
    u64 last_tick=armGetSystemTick(), clock_carry=0;
    while (appletMainLoop()) {
#ifdef DINO_EMULATOR_SELFTEST
        ++guest_frame_id; /* render iteration ID, never host timing */
#endif
        padUpdate(&pad);
        const u64 down=padGetButtonsDown(&pad);
        const u64 held=padGetButtons(&pad);
#ifdef DINO_EMULATOR_SELFTEST
        /* A pad edge may arrive in a zero-game-tick render iteration.
         * Retain its origin until the 60-Hz step consumes the buffered
         * DINO_ARENA_COUNTER action; do not require same-frame timing. */
        if (guest_audio_stress_done && guest_controller_done &&
            (down&HidNpadButton_ZR))
            guest_counter_zr_edge_pending=true;
        if (guest_live_spar_armed && !guest_live_counter_done &&
            (down&HidNpadButton_ZR))
            guest_live_zr_edge_pending=true;
#endif
        u64 now=armGetSystemTick();
        u64 elapsed_ns=armTicksToNs(now-last_tick);
        last_tick=now;
        if (elapsed_ns>250000000ULL) elapsed_ns=250000000ULL;
#ifdef DINO_EMULATOR_SELFTEST
        const uint32_t guest_ack_before_this_frame=guest_ack_tick_count;
        uint32_t guest_frame_full_game_ticks=0;
#endif
        if (down & HidNpadButton_Plus) break;
        if ((down & HidNpadButton_ZL) && gfx) {
            arena_active=!arena_active;
            arena_clock_carry=0;
            pending_actions=0;
            counter_feedback_ticks=0;
            demo_active=false;
            demo_complete=false;
            demo_ticks=0;
            demo_witness=DINO_WITNESS_INIT;
            /* Leaving the arena discards any unfinished cue envelopes
             * and releases audout. Re-entry starts a fresh PCM timeline. */
            if (arena_active) (void)dino_switch_sound_open();
            else dino_switch_sound_close();
        }
        if (arena_active) {
            if (down & HidNpadButton_Minus) {
                /* ROM-free built-in deterministic test: no game assets,
                 * no emulator-specific scripts or private input captures. */
                dino_arena_reset(&arena);
                demo_ticks=0;
                demo_witness=DINO_WITNESS_INIT;
                demo_active=true;
                demo_complete=false;
                pending_actions=0;
                counter_feedback_ticks=0;
                arena_clock_carry=0;
                /* The desktop witness starts from a reset SFX timeline.
                 * Make NRO replay audio equally reproducible, including
                 * after manually played attacks. Silent fallback remains
                 * harmless if audout cannot be initialized. */
                dino_switch_sound_close();
                (void)dino_switch_sound_open();
            } else if (down & HidNpadButton_Y) {
#ifdef DINO_EMULATOR_SELFTEST
                if (guest_natural_counter_done &&
                    guest_audio_stress_done && guest_controller_done &&
                    guest_counter_hid_done) {
                    guest_live_reset_seen=true;
                    guest_live_spar_armed=false;
                    guest_live_ready_written=false;
                    guest_live_counter_done=false;
                    guest_live_zr_edge_pending=false;
                    guest_live_spar_origin=0u;
                }
                if (guest_done && !guest_controller_active &&
                    !guest_controller_done) {
                    /* Evidence exists only if NeXium delivers an ACTUAL
                     * Y press. Never self-inject input or infer it from
                     * the automated 180-tick replay. */
                    guest_controller_witness=fopen(
                        "sdmc:/cadillacs-controller-selftest.csv","w");
                    if (guest_controller_witness) {
                        fputs("event,flags,player_x,sparring\n",
                              guest_controller_witness);
                        fputs("RESET,1,90,0\n",guest_controller_witness);
                        fflush(guest_controller_witness);
                        guest_controller_flags=1u;
                        guest_controller_active=true;
                        guest_hid_timeline=fopen(
                            "sdmc:/cadillacs-hid-timeline.csv","w");
                        if (guest_hid_timeline) {
                            fputs("event,tick,player_x,sparring,event_mask\n"
                                  "RESET,0,90,0,0\n",guest_hid_timeline);
                            fflush(guest_hid_timeline);
                            guest_hid_phase=1u;
                        }
                    }
                }
#endif
                dino_arena_reset(&arena);
                demo_ticks=0;
                demo_witness=DINO_WITNESS_INIT;
                demo_active=false;
                demo_complete=false;
                arena_clock_carry=0;
                pending_actions=0;
                counter_feedback_ticks=0;
            }
            uint32_t held_arena=0;
            if (held & HidNpadButton_Left) held_arena|=DINO_ARENA_LEFT;
            if (held & HidNpadButton_Right) held_arena|=DINO_ARENA_RIGHT;
            if (held & HidNpadButton_Up) held_arena|=DINO_ARENA_UP;
            if (held & HidNpadButton_Down) held_arena|=DINO_ARENA_DOWN;
            if (down & HidNpadButton_A) pending_actions|=DINO_ARENA_ATTACK;
            if (down & HidNpadButton_B) pending_actions|=DINO_ARENA_JUMP;
            if (down & HidNpadButton_X) pending_actions|=DINO_ARENA_TOGGLE_SPAR;
            if (down & HidNpadButton_ZR) pending_actions|=DINO_ARENA_COUNTER;
            arena_clock_carry+=elapsed_ns*60u;
            uint32_t arena_ticks=(uint32_t)(arena_clock_carry/1000000000ULL);
#ifdef DINO_EMULATOR_SELFTEST
            guest_frame_full_game_ticks=arena_ticks;
#endif
            arena_clock_carry%=1000000000ULL;
            for (uint32_t i=0;i<arena_ticks;++i) {
                uint32_t step_held=held_arena;
                uint32_t step_pressed=i==0 ? pending_actions : 0u;
                if (demo_complete) break; /* stable screenshot/witness */
                if (demo_active) {
                    if (!dino_replay_input(demo_ticks,
                                           &step_held,&step_pressed))
                        break; /* invalid trace never runs unknown input */
                }
                /* CI-only: pre-event state from the *visible* player arena,
                 * not from guest_natural_counter or any staged dummy. */
#ifdef DINO_EMULATOR_SELFTEST
                const DinoArena live_before=arena;
#endif
                dino_arena_step(&arena,step_held,step_pressed);
                counter_feedback_ticks=dino_arena_counter_feedback_tick(
                    counter_feedback_ticks,arena.events);
#ifdef DINO_EMULATOR_SELFTEST
                /* Stage 234: optional external HID ZR proof, only after the
                 * existing 900-tick audio stress evidence is finalized.
                 * The trigger MUST be libnx padGetButtonsDown AND the
                 * actual pending edge consumed by this game tick.
                 * This isolated prepared arena avoids modifying the live
                 * game, controller sequence or historical audio witnesses. */
                if (guest_audio_stress_done && guest_controller_done &&
                    !demo_active && !guest_counter_hid_done &&
                    guest_counter_zr_edge_pending &&
                    (step_pressed&DINO_ARENA_COUNTER)) {
                    guest_counter_zr_edge_pending=false;
                    guest_counter_hid_done=true;
                    DinoArena test_counter;
                    dino_arena_reset(&test_counter);
                    test_counter.x=220;
                    dino_arena_step(&test_counter,0u,DINO_ARENA_TOGGLE_SPAR);
                    const DinoArena ready_counter=test_counter;
                    /* The edge is real libnx HID, the ready training scene
                     * is deliberately controlled and independent. Compute
                     * the complete first 800-frame synthesized PCM digest
                     * using the same portable C engine, not a preset hash. */
                    dino_arena_step(&test_counter,0u,
                                    step_pressed&DINO_ARENA_COUNTER);
                    DinoSfx counter_sfx;
                    int16_t counter_pcm[DINO_SFX_TICK_FRAMES*2u];
                    dino_sfx_reset(&counter_sfx);
                    dino_sfx_events(&counter_sfx,test_counter.events);
                    dino_sfx_render_tick(&counter_sfx,counter_pcm,
                                         DINO_SFX_TICK_FRAMES);
                    unsigned counter_pcm_nonzero=0u;
                    for (unsigned j=0u;j<2u*DINO_SFX_TICK_FRAMES;++j)
                        if (counter_pcm[j]) { counter_pcm_nonzero=1u; break; }
                    const uint64_t counter_pcm_hash=dino_pcm_witness_feed(
                        DINO_PCM_WITNESS_INIT,counter_pcm,DINO_SFX_TICK_FRAMES);
                    const char *const path="sdmc:/cadillacs-counter-hid.csv";
                    FILE *proof=fopen(path,"w");
                    if (proof) {
                        fprintf(proof,"phase,tick,player_hp,enemy_hp,windup,"
                                "stun,cooldown,event_mask,hid_edge,"
                                "pcm_nonzero,pcm_fnv64\n");
                        fprintf(proof,
                                "READY,%u,%u,%u,%u,%u,%u,%u,0,0,%016llX\n",
                                (unsigned)ready_counter.ticks,
                                (unsigned)ready_counter.player_hp,
                                (unsigned)ready_counter.dummy_hp,
                                (unsigned)ready_counter.dummy_windup,
                                (unsigned)ready_counter.dummy_hitstun,
                                (unsigned)ready_counter.dummy_cooldown,
                                (unsigned)ready_counter.events,
                                (unsigned long long)DINO_PCM_WITNESS_INIT);
                        fprintf(proof,"HID_COUNTER,%u,%u,%u,%u,%u,%u,%u,1,"
                                "%u,%016llX\n",
                                (unsigned)test_counter.ticks,
                                (unsigned)test_counter.player_hp,
                                (unsigned)test_counter.dummy_hp,
                                (unsigned)test_counter.dummy_windup,
                                (unsigned)test_counter.dummy_hitstun,
                                (unsigned)test_counter.dummy_cooldown,
                                (unsigned)test_counter.events,
                                counter_pcm_nonzero,
                                (unsigned long long)counter_pcm_hash);
                        (void)fclose(proof);
                    }
                }
                /* Separate real libnx ZR edge during an AI-created
                 * telegraph, not a preloaded 12-tick dummy windup.
                 * The independent practice arena advances ONCE for every
                 * real 60Hz guest simulation tick. Host may react to the
                 * ready marker, but a host attempt cannot create proof. */
                if (guest_counter_hid_done &&
                    !guest_natural_counter_active) {
                    dino_arena_reset(&guest_natural_counter);
                    guest_natural_counter_active=true;
                }
                if (guest_natural_counter_active &&
                    !guest_natural_counter_done &&
                    guest_natural_counter.ticks<400u) {
                    const DinoArena before=guest_natural_counter;
                    const bool natural_zr_edge=
                        guest_counter_zr_edge_pending &&
                        (step_pressed&DINO_ARENA_COUNTER)!=0u;
                    const uint32_t natural_pressed=before.ticks==0u ?
                        DINO_ARENA_TOGGLE_SPAR :
                        (natural_zr_edge ? DINO_ARENA_COUNTER : 0u);
                    if (natural_zr_edge)
                        guest_counter_zr_edge_pending=false;
                    dino_arena_step(&guest_natural_counter,0u,
                                    natural_pressed);
                    if (!guest_natural_ready_written &&
                        guest_natural_counter.ticks==116u &&
                        guest_natural_counter.x==90 &&
                        guest_natural_counter.dummy_x==134 &&
                        guest_natural_counter.dummy_windup==12u &&
                        guest_natural_counter.player_hp==5 &&
                        guest_natural_counter.dummy_hp==3) {
                        /* Marker is only a host timing hint, not success.
                         * The emulator guest must still see a second real
                         * padGetButtonsDown(ZR) at the actual windup tick. */
                        FILE *ready=fopen(
                            "sdmc:/cadillacs-natural-counter-ready.csv","w");
                        if (ready) {
                            fputs("event,tick,player_x,enemy_x,windup,"
                                  "player_hp,enemy_hp\n"
                                  "NATURAL_READY,116,90,134,12,5,3\n",
                                  ready);
                            (void)fclose(ready);
                        }
                        guest_natural_ready_written=true;
                    }
                    if (natural_zr_edge &&
                        before.ticks>=116u && before.ticks<128u &&
                        before.x==90 && before.dummy_x==134 &&
                        before.player_hp==5 && before.dummy_hp==3 &&
                        before.dummy_windup>=1u &&
                        before.dummy_windup<=12u &&
                        guest_natural_counter.events==DINO_EVT_COUNTER &&
                        guest_natural_counter.player_hp==5 &&
                        guest_natural_counter.dummy_hp==3 &&
                        guest_natural_counter.dummy_windup==0u &&
                        guest_natural_counter.dummy_hitstun==9u &&
                        guest_natural_counter.dummy_cooldown==48u) {
                        DinoSfx sfx;
                        int16_t pcm[DINO_SFX_TICK_FRAMES*2u];
                        dino_sfx_reset(&sfx);
                        dino_sfx_events(&sfx,guest_natural_counter.events);
                        dino_sfx_render_tick(&sfx,pcm,DINO_SFX_TICK_FRAMES);
                        unsigned nonzero=0u;
                        for (unsigned j=0u;
                             j<2u*DINO_SFX_TICK_FRAMES;++j)
                            if (pcm[j]) { nonzero=1u; break; }
                        const uint64_t hash=dino_pcm_witness_feed(
                            DINO_PCM_WITNESS_INIT,pcm,DINO_SFX_TICK_FRAMES);
                        FILE *proof=fopen(
                            "sdmc:/cadillacs-natural-counter-hid.csv","w");
                        if (proof) {
                            fputs("event,tick,player_x,enemy_x,"
                                  "pre_windup,player_hp,enemy_hp,"
                                  "post_windup,stun,cooldown,event_mask,"
                                  "hid_edge,pcm_nonzero,pcm_fnv64\n",
                                  proof);
                            fprintf(proof,
                                    "NATURAL_HID_COUNTER,%u,%d,%d,%u,"
                                    "%u,%u,%u,%u,%u,%u,1,%u,%016llX\n",
                                    (unsigned)guest_natural_counter.ticks,
                                    guest_natural_counter.x,
                                    guest_natural_counter.dummy_x,
                                    (unsigned)before.dummy_windup,
                                    (unsigned)guest_natural_counter.player_hp,
                                    (unsigned)guest_natural_counter.dummy_hp,
                                    (unsigned)guest_natural_counter.dummy_windup,
                                    (unsigned)guest_natural_counter.dummy_hitstun,
                                    (unsigned)guest_natural_counter.dummy_cooldown,
                                    (unsigned)guest_natural_counter.events,
                                    nonzero,(unsigned long long)hash);
                            (void)fclose(proof);
                        }
                        guest_natural_counter_done=true;
                    }
                }
                /* Stage 246: real X sparring on the actual drawn arena.
                 * The initial Y reset must also have been a libnx edge.
                 * Simulated steps, not host stopwatch time, define origin. */
                if (guest_live_reset_seen && !guest_live_spar_armed &&
                    (step_pressed&DINO_ARENA_TOGGLE_SPAR) &&
                    (arena.events&DINO_EVT_SPAR_TOGGLE) &&
                    arena.sparring && arena.x==90 && arena.dummy_x==249 &&
                    arena.player_hp==5 && arena.dummy_hp==3 &&
                    arena.facing_right==1u && !demo_active &&
                    !demo_complete) {
                    guest_live_spar_armed=true;
                    guest_live_spar_origin=arena.ticks;
                }
                if (guest_live_spar_armed && !guest_live_counter_done &&
                    arena.ticks>=guest_live_spar_origin) {
                    const uint32_t relative_tick=
                        arena.ticks-guest_live_spar_origin+1u;
                    if (!guest_live_ready_written &&
                        relative_tick==116u &&
                        arena.x==90 && arena.dummy_x==134 &&
                        arena.dummy_windup==12u &&
                        arena.player_hp==5 && arena.dummy_hp==3 &&
                        arena.sparring && !demo_active && !demo_complete) {
                        FILE *ready=fopen(
                            "sdmc:/cadillacs-live-counter-ready.csv","w");
                        if (ready) {
                            fputs("event,tick,player_x,enemy_x,windup,"
                                  "player_hp,enemy_hp\n"
                                  "LIVE_READY,116,90,134,12,5,3\n",ready);
                            (void)fclose(ready);
                        }
                        guest_live_ready_written=true;
                    }
                    const bool received_live_zr=
                        guest_live_zr_edge_pending &&
                        (step_pressed&DINO_ARENA_COUNTER)!=0u;
                    if (received_live_zr)
                        guest_live_zr_edge_pending=false;
                    if (guest_live_ready_written && received_live_zr &&
                        relative_tick>=117u && relative_tick<=128u &&
                        live_before.x==90 && live_before.dummy_x==134 &&
                        live_before.player_hp==5 && live_before.dummy_hp==3 &&
                        live_before.dummy_windup==129u-relative_tick &&
                        live_before.sparring &&
                        arena.events==DINO_EVT_COUNTER &&
                        arena.player_hp==5 && arena.dummy_hp==3 &&
                        arena.dummy_windup==0u &&
                        arena.dummy_hitstun==9u &&
                        arena.dummy_cooldown==48u) {
                        DinoSfx event_sfx;
                        int16_t pcm[DINO_SFX_TICK_FRAMES*2u];
                        dino_sfx_reset(&event_sfx);
                        dino_sfx_events(&event_sfx,arena.events);
                        dino_sfx_render_tick(&event_sfx,pcm,
                                             DINO_SFX_TICK_FRAMES);
                        unsigned nonzero=0u;
                        for (unsigned j=0u;
                             j<2u*DINO_SFX_TICK_FRAMES;++j)
                            if (pcm[j]) { nonzero=1u; break; }
                        const uint64_t pcm_hash=dino_pcm_witness_feed(
                            DINO_PCM_WITNESS_INIT,pcm,DINO_SFX_TICK_FRAMES);
                        FILE *proof=fopen(
                            "sdmc:/cadillacs-live-counter-hid.csv","w");
                        if (proof) {
                            fputs("event,tick,player_x,enemy_x,"
                                  "pre_windup,player_hp,enemy_hp,"
                                  "post_windup,stun,cooldown,event_mask,"
                                  "hid_edge,pcm_nonzero,pcm_fnv64\n",proof);
                            fprintf(proof,
                                    "LIVE_HID_COUNTER,%u,%d,%d,%u,"
                                    "%u,%u,%u,%u,%u,%u,1,%u,%016llX\n",
                                    (unsigned)relative_tick,
                                    arena.x,arena.dummy_x,
                                    (unsigned)live_before.dummy_windup,
                                    (unsigned)arena.player_hp,
                                    (unsigned)arena.dummy_hp,
                                    (unsigned)arena.dummy_windup,
                                    (unsigned)arena.dummy_hitstun,
                                    (unsigned)arena.dummy_cooldown,
                                    (unsigned)arena.events,nonzero,
                                    (unsigned long long)pcm_hash);
                            (void)fclose(proof);
                        }
                        guest_live_counter_done=true;
                    }
                }
                if (guest_controller_active && !demo_active) {
                    /* A second witness records the ordered effect timeline.
                     * A misordered key sequence never advances the phase.
                     * It cannot be populated by the built-in C replay. */
                    if (guest_hid_timeline && guest_hid_phase==1u &&
                        (step_held&DINO_ARENA_RIGHT) && arena.x>90) {
                        fprintf(guest_hid_timeline,"MOVE,%u,%d,%u,%u\n",
                                (unsigned)arena.ticks,arena.x,
                                (unsigned)arena.sparring,
                                (unsigned)arena.events);
                        fflush(guest_hid_timeline);
                        guest_hid_phase=2u;
                    } else if (guest_hid_timeline &&
                               guest_hid_phase==2u &&
                               (step_pressed&DINO_ARENA_ATTACK) &&
                               (arena.events&DINO_EVT_PLAYER_SWING)) {
                        fprintf(guest_hid_timeline,"ATTACK,%u,%d,%u,%u\n",
                                (unsigned)arena.ticks,arena.x,
                                (unsigned)arena.sparring,
                                (unsigned)arena.events);
                        fflush(guest_hid_timeline);
                        guest_hid_phase=3u;
                    } else if (guest_hid_timeline &&
                               guest_hid_phase==3u &&
                               (step_pressed&DINO_ARENA_JUMP) &&
                               (arena.events&DINO_EVT_JUMP_START)) {
                        fprintf(guest_hid_timeline,"JUMP,%u,%d,%u,%u\n",
                                (unsigned)arena.ticks,arena.x,
                                (unsigned)arena.sparring,
                                (unsigned)arena.events);
                        fflush(guest_hid_timeline);
                        guest_hid_phase=4u;
                    } else if (guest_hid_timeline &&
                               guest_hid_phase==4u &&
                               (step_pressed&DINO_ARENA_TOGGLE_SPAR) &&
                               (arena.events&DINO_EVT_SPAR_TOGGLE) &&
                               arena.sparring) {
                        fprintf(guest_hid_timeline,
                                "SPAR,%u,%d,%u,%u\n"
                                "DONE,%u,%d,%u,%u\n",
                                (unsigned)arena.ticks,arena.x,
                                (unsigned)arena.sparring,
                                (unsigned)arena.events,
                                (unsigned)arena.ticks,arena.x,
                                (unsigned)arena.sparring,
                                (unsigned)arena.events);
                        fflush(guest_hid_timeline);
                        guest_hid_phase=5u;
                    }
                    /* Check gameplay EFFECTS, not just raw button bits.
                     * The replay trace never contributes to this witness. */
                    if ((held & HidNpadButton_Right) && arena.x>90)
                        guest_controller_flags|=2u;
                    /* Edge-triggered inputs may be buffered across a
                     * render frame that contains no 60Hz simulation tick. */
                    if ((step_pressed&DINO_ARENA_ATTACK) &&
                        (arena.events&DINO_EVT_PLAYER_SWING))
                        guest_controller_flags|=4u;
                    if ((step_pressed&DINO_ARENA_JUMP) &&
                        (arena.events&DINO_EVT_JUMP_START))
                        guest_controller_flags|=8u;
                    if ((step_pressed&DINO_ARENA_TOGGLE_SPAR) &&
                        (arena.events&DINO_EVT_SPAR_TOGGLE) && arena.sparring)
                        guest_controller_flags|=16u;
                    if (guest_controller_flags==31u &&
                        guest_controller_witness) {
                        fprintf(guest_controller_witness,
                                "INPUT_DONE,%u,%d,%u\n",
                                (unsigned)guest_controller_flags,arena.x,
                                (unsigned)arena.sparring);
                        fflush(guest_controller_witness);
                        guest_controller_active=false;
                        guest_controller_done=true;
                    }
                }
#endif
                if (demo_active)
                    demo_witness=dino_replay_witness_tick(demo_witness,&arena);
                /* Experimental, opt-in, guest-only extra nonblocking
                 * release poll immediately before each later catch-up
                 * tick. The ordinary game and default self-test keep
                 * their historical exact poll schedule. */
#if defined(DINO_EMULATOR_SELFTEST) && \
    defined(DINO_AUDIO_EXPERIMENT_MID_BATCH_POLL)
                if (guest_audio_stress && !guest_audio_stress_done &&
                    arena_ticks>=2u && i>0u)
                    dino_switch_sound_guest_mid_batch_poll();
#endif
                /* Consume precisely the event from this simulated tick. */
                dino_switch_sound_step(arena.events);
#ifdef DINO_EMULATOR_SELFTEST
                if (guest_audio_stress && !guest_audio_stress_done) {
                    /* Attribute the just-consumed guest audio tick to
                     * the render iteration's scheduled batch size.
                     * No sleeps, resampling or queue-policy changes. */
                    DinoSoundDiagnostics audio_now;
                    dino_switch_sound_diagnostics(&audio_now);
                    const uint32_t skipped_now =
                        audio_now.skipped-guest_batch.previous_skips;
                    guest_batch.previous_skips=audio_now.skipped;
                    const uint32_t released_now=
                        audio_now.released-guest_batch.previous_released;
                    guest_batch.previous_released=audio_now.released;
                    const uint32_t full_now=
                        audio_now.pre_poll_full_steps-guest_batch.previous_full;
                    const uint32_t recovered_now=
                        audio_now.pre_poll_recovered_steps-
                        guest_batch.previous_recovered;
                    guest_batch.previous_full=audio_now.pre_poll_full_steps;
                    guest_batch.previous_recovered=
                        audio_now.pre_poll_recovered_steps;
                    const uint32_t submitted_now=
                        audio_now.submitted-guest_batch.previous_submitted;
                    guest_batch.previous_submitted=audio_now.submitted;
                    const uint32_t mid_calls_total=
                        dino_switch_sound_guest_mid_batch_calls();
                    const uint32_t mid_releases_total=
                        dino_switch_sound_guest_mid_batch_releases();
                    const uint32_t mid_calls_now=
                        mid_calls_total-guest_batch.previous_mid_calls;
                    const uint32_t mid_releases_now=
                        mid_releases_total-guest_batch.previous_mid_releases;
                    guest_batch.previous_mid_calls=mid_calls_total;
                    guest_batch.previous_mid_releases=mid_releases_total;
                    if (guest_ack_tick_collecting) {
                        /* Poll discovery tick, not actual service timestamp.
                         * Only fixed-size RAM copies within 900 game ticks. */
                        const uint32_t observation[DINO_GUEST_ACK_TRACE_COLUMNS]={
                            guest_ack_tick_count+1u,guest_frame_id,
                            arena_ticks,i,released_now,mid_releases_now,
                            mid_calls_now,submitted_now,skipped_now,
                            full_now,recovered_now,audio_now.pending,
                            audio_now.audio_errors
                        };
                        if (dino_guest_ack_trace_append(
                                &s_guest_ack_tick_trace,observation))
                            ++guest_ack_tick_count;
                        else
                            guest_ack_tick_collecting=false; /* fail closed */
                    }
                    if (arena_ticks>=2u) {
                        ++guest_batch.batched_ticks;
                        guest_batch.batched_skips+=skipped_now;
                        /* i is the position within the scheduled frame. */
                        if (i==0u) {
                            ++guest_batch.first_ticks;
                            guest_batch.first_skips+=skipped_now;
                            guest_batch.first_releases+=released_now;
                            guest_batch.first_full+=full_now;
                            guest_batch.first_recovered+=recovered_now;
                        } else {
                            ++guest_batch.later_ticks;
                            guest_batch.later_skips+=skipped_now;
                            guest_batch.later_releases+=released_now;
                            guest_batch.later_full+=full_now;
                            guest_batch.later_recovered+=recovered_now;
                        }
                        if (guest_batch.previous_frame_id!=guest_frame_id) {
                            ++guest_batch.batched_frames;
                            guest_batch.previous_frame_id=guest_frame_id;
                        }
                    } else {
                        ++guest_batch.single_ticks;
                        guest_batch.single_skips+=skipped_now;
                        guest_batch.single_releases+=released_now;
                    }
                    if (arena_ticks>guest_batch.largest_batch)
                        guest_batch.largest_batch=arena_ticks;
                }
                if (guest_controller_done && !guest_audio_stress_done) {
                    /* The completed native Y/Right/A/B/X HID witness,
                     * not the built-in 180-tick replay, triggers this. */
                    if (!guest_audio_stress) {
                        guest_audio_stress=fopen(
                            "sdmc:/cadillacs-audio-stress.csv","w");
                        if (guest_audio_stress) {
                            fputs("event,elapsed_ticks,arena_ticks,audio_ticks,"
                                  "pcm_ticks,active,queue_valid,pending,"
                                  "submitted,released,skipped,audio_errors,"
                                  "pcm_fnv64,full_queue_skips,"
                                  "inactive_backend_skips,unexpected_slot_skips,"
                                  "max_consecutive_skips,single_frame_ticks,"
                                  "batched_frame_ticks,single_frame_skips,"
                                  "batched_frame_skips,batched_render_frames,"
                                  "max_ticks_per_render_frame,"
                                  "pre_poll_full_steps,"
                                  "pre_poll_recovered_steps,"
                                  "batched_first_tick_steps,"
                                  "batched_later_tick_steps,"
                                  "batched_first_tick_skips,"
                                  "batched_later_tick_skips,"
                                  "batched_first_full_before_poll,"
                                  "batched_first_recovered_after_poll,"
                                  "batched_later_full_before_poll,"
                                  "batched_later_recovered_after_poll,"
                                  "single_frame_released_pages,"
                                  "batched_first_released_pages,"
                                  "batched_later_released_pages,"
                                  "guest_mid_batch_extra_poll_enabled,"
                                  "guest_mid_batch_extra_poll_calls,"
                                  "guest_mid_batch_extra_poll_released_pages\n",
                                  guest_audio_stress);
                            guest_audio_stress_start=arena.ticks;
                            /* The START row follows the first sound step.
                             * Correlate only the subsequent 900 steps. */
                            DinoSoundDiagnostics at_start;
                            dino_switch_sound_diagnostics(&at_start);
                            guest_batch=(DinoGuestBatchStats){0};
                            guest_batch.previous_skips=at_start.skipped;
                            guest_batch.previous_submitted=at_start.submitted;
                            guest_batch.previous_mid_calls=
                                dino_switch_sound_guest_mid_batch_calls();
                            guest_batch.previous_mid_releases=
                                dino_switch_sound_guest_mid_batch_releases();
                            guest_batch.previous_released=at_start.released;
                            guest_batch.previous_full=
                                at_start.pre_poll_full_steps;
                            guest_batch.previous_recovered=
                                at_start.pre_poll_recovered_steps;
                            guest_audio_stress_row(guest_audio_stress,
                                                   "START",0u,&arena,
                                                   &guest_batch);
                            guest_ack_tick_count=0;
                            dino_guest_ack_trace_reset(&s_guest_ack_tick_trace);
                            guest_ack_tick_collecting=true;
                            dino_guest_frame_clock_reset(&s_guest_frame_clock);
                            guest_frame_clock_started=true;
                            guest_frame_clock_done=false;
                            guest_frame_clock_flushed=false;
#if defined(DINO_AUDIO_EXPERIMENT_RESUME_RAMP)
                            guest_resume_start_count=
                                dino_switch_sound_guest_resume_ramp_applications();
                            guest_resume_start_full=at_start.full_queue_skips;
                            guest_resume_initial_pending=
                                dino_switch_sound_guest_resume_ramp_pending();
                            guest_resume_report_ready=false;
                            guest_resume_report_written=false;
#endif
                        }
                    } else {
                        uint32_t elapsed=arena.ticks-guest_audio_stress_start;
                        if (elapsed==guest_audio_stress_next) {
                            guest_audio_stress_row(
                                guest_audio_stress,
                                elapsed==DINO_GUEST_AUDIO_STRESS_TICKS
                                    ? "STRESS_DONE" : "CHECKPOINT",
                                elapsed,&arena,&guest_batch);
                            if (elapsed==DINO_GUEST_AUDIO_STRESS_TICKS) {
                                guest_audio_stress_done=true;
#if defined(DINO_AUDIO_EXPERIMENT_RESUME_RAMP)
                                /* Capture stop state at the exact 900th
                                 * simulation tick; serialize after render. */
                                DinoSoundDiagnostics resume_end;
                                dino_switch_sound_diagnostics(&resume_end);
                                guest_resume_end_full=resume_end.full_queue_skips;
                                guest_resume_end_count=
                                    dino_switch_sound_guest_resume_ramp_applications();
                                guest_resume_final_pending=
                                    dino_switch_sound_guest_resume_ramp_pending();
                                guest_resume_report_ready=true;
#endif
                                fclose(guest_audio_stress);
                                guest_audio_stress=NULL;
                                guest_ack_tick_collecting=false;
                                guest_frame_clock_done=true;
                                /* Delayed SD write occurs AFTER the last
                                 * measured tick, not during 60Hz simulation. */
                                const char *const ack_path=
                                    "sdmc:/cadillacs-audio-ack-ticks.csv";
                                FILE *ack_output=fopen(ack_path,"w");
                                if (ack_output) {
                                    const bool complete=
                                        dino_guest_ack_trace_write_csv(
                                            ack_output,&s_guest_ack_tick_trace);
                                    const int closed=fclose(ack_output);
                                    if (!complete || closed!=0)
                                        (void)remove(ack_path);
                                }
                            } else {
                                guest_audio_stress_next+=
                                    DINO_GUEST_AUDIO_STRESS_PERIOD;
                            }
                        }
                    }
                }
#endif
                if (demo_active && ++demo_ticks==DINO_REPLAY_TICKS) {
                    demo_active=false;
                    demo_complete=true;
                    break; /* remain frozen at independently known state */
                }
            }
            if (demo_complete) arena_clock_carry=0;
            if (arena_ticks) pending_actions=0;
            clock_carry=0;
        } else {
            arena_clock_carry=0;
            pending_actions=0;
            counter_feedback_ticks=0;
        }
        if (!arena_active && (down & HidNpadButton_X) && scene_rgba)
            show_scene=!show_scene;
        if (!arena_active && show_scene && scene_rgba && scene && sequence_blob) {
            bool redraw=false;
#ifdef DINO_SYNTHETIC_SCENE_HOST_VISIBLE_313
            if (synthetic_scene_guest_ready && synthetic_guest_rows>0u &&
                synthetic_guest_rows<14u) {
                /* Distinct immutable mailbox per scene index. NeXium's
                 * emulated FS may cache an open file's contents/inode;
                 * replacing NEXT,0 with NEXT,1 at the SAME path can leave
                 * subsequent guest reads observing the stale first ack.
                 * Never reuse a mailbox name between frame transitions. */
                char ack_path[96];
                snprintf(ack_path,sizeof(ack_path),
                         "sdmc:/cadillacs-synthetic-scene-next-%02u.txt",
                         (unsigned)playback.index);
                FILE *ack=fopen(ack_path,"rb");
                if (ack) {
                    char line[40]={0};
                    size_t got=fread(line,1,sizeof(line)-1u,ack);
                    fclose(ack);
                    unsigned ack_index=UINT32_MAX;
                    if (got>0u && sscanf(line,"NEXT,%u",&ack_index)==1 &&
                        ack_index==playback.index &&
                        (synthetic_guest_seen&(1u<<ack_index))!=0u)
                        redraw=cps1_playback_step(&playback,&sequence,1);
                }
            }
#endif
            if (down & HidNpadButton_A) playback.paused=!playback.paused;
            if (down & HidNpadButton_L) cps1_playback_speed(&playback,-1);
            if (down & HidNpadButton_R) cps1_playback_speed(&playback,1);
            if (down & HidNpadButton_B) redraw=cps1_playback_step(&playback,&sequence,1);
            if (down & HidNpadButton_Y) redraw=cps1_playback_step(&playback,&sequence,-1);
            /* Fixed 60 Hz virtual clock, not a frame-counted sleep loop.
             * Resume after tiles does not replay accumulated hidden time. */
            clock_carry+=elapsed_ns*60u;
            uint32_t ticks=(uint32_t)(clock_carry/1000000000ULL);
            clock_carry%=1000000000ULL;
            if (cps1_playback_advance(&playback,&sequence,ticks)) redraw=true;
            if (redraw && cps1_sequence_frame(&sequence,playback.index,scene))
                cps1_scene_render(gfx,CPS1_GFX_BYTES,scene,
                                  scene_rgba,CPS1_SCENE_RGBA_BYTES);
        } else {
            clock_carry=0;
        }
        if (!arena_active && show_scene && scene_rgba && scene && !sequence_blob) {
            /* Free navigation: does not advance the game's CPU or AI.
             * Sprites remain at their captured screen coordinates.
             */
            const int speed=(held & HidNpadButton_ZR) ? 12 : 3;
            int dx=0,dy=0;
            if (held & HidNpadButton_Left) dx-=speed;
            if (held & HidNpadButton_Right) dx+=speed;
            if (held & HidNpadButton_Up) dy-=speed;
            if (held & HidNpadButton_Down) dy+=speed;
            bool dirty=cps1_scene_pan(scene,dx,dy);
            if (down & HidNpadButton_A) {
                memcpy(scene->scrollx,initial_scrollx,sizeof(initial_scrollx));
                memcpy(scene->scrolly,initial_scrolly,sizeof(initial_scrolly));
                dirty=true;
            }
            if (dirty)
                cps1_scene_render(gfx,CPS1_GFX_BYTES,scene,
                                  scene_rgba,CPS1_SCENE_RGBA_BYTES);
        }
        unsigned next=page;
        if (!arena_active && !show_scene && (down & HidNpadButton_Left) && next>0) --next;
        if (!arena_active && !show_scene && (down & HidNpadButton_Right) && next+1<PAGE_COUNT) ++next;
        if (!arena_active && !show_scene && (down & HidNpadButton_Up)) next=next>=16?next-16:0;
        if (!arena_active && !show_scene && (down & HidNpadButton_Down)) next=next+16<PAGE_COUNT?next+16:PAGE_COUNT-1;
        if (!arena_active && !show_scene && (down & HidNpadButton_L)) next=next>=8?next-8:0;
        if (!arena_active && !show_scene && (down & HidNpadButton_R)) next=next+8<PAGE_COUNT?next+8:PAGE_COUNT-1;
        if (!arena_active && !show_scene && (down & HidNpadButton_A)) invert=!invert;
        if (!arena_active && !show_scene && (down & HidNpadButton_B)) transparent=!transparent;
        if (!arena_active && !show_scene && (down & HidNpadButton_Y)) grid=!grid;
        if (!arena_active && gfx && next != page && cache_page(gfx,next)) page=next;
        u32 stride=0;
        uint32_t *frame=(uint32_t*)framebufferBegin(&fb,&stride);
        if (!frame) break;
#ifdef DINO_EMULATOR_SELFTEST
        /* Capture literal colors from the SAME pixel buffer the native
         * game renderer submits. A successful ZR state witness alone
         * is NOT framebuffer evidence. No host screenshot is involved.
         * Save sampled values, not pointer data beyond framebufferEnd. */
        bool guest_counter_frame_pixels_valid=false;
        bool guest_counter_token_frame_valid=false;
        uint32_t guest_counter_pixel_caption=0u;
        uint32_t guest_counter_pixel_impact=0u;
        uint32_t guest_counter_pixel_player=0u;
        uint32_t guest_counter_pixel_background=0u;
        uint32_t guest_counter_pixel_tick=0u;
        uint32_t guest_counter_pixel_ttl=0u;
        uint32_t guest_counter_pixel_flash=0u;
#endif
        if (arena_active) {
            arena_frame(frame,stride/sizeof(uint32_t),&arena,gfx!=NULL,
                        demo_ticks,demo_active,demo_complete,demo_witness,
                        counter_feedback_ticks);
#ifdef DINO_EMULATOR_SELFTEST
            /* Stage 253: draw a unique render-iteration token on each
             * submitted feedback frame, visible to the host X11 sampler.
             * Unlike an event timestamp, this identifies real pixel data. */
            if (guest_live_counter_done &&
                counter_feedback_ticks>0u &&
                arena.dummy_impact_flash>0u &&
                arena.x==90 && arena.dummy_x==134 &&
                arena.player_hp==5 && arena.dummy_hp==3 &&
                !demo_active && !demo_complete &&
                !guest_token_trace_written) {
                const unsigned pitch_px=(unsigned)(stride/sizeof(uint32_t));
                const uint16_t token=(uint16_t)guest_frame_id;
                dino_counter_token_draw(frame,pitch_px,token);
                guest_counter_token_frame_valid=
                    dino_counter_token_check(frame,pitch_px,token);
            }
            /* 'COUNTER!' glyph C has an illuminated pixel at (801,670).
             * Enemy cross at (465,335), body at (334,425), neutral lane
             * ground at (100,640). These fixed pixels have independent
             * layout regions and must all match their renderer colors. */
            if (guest_live_counter_done &&
                !guest_counter_framebuffer_written &&
                counter_feedback_ticks>0u &&
                arena.dummy_impact_flash>0u &&
                arena.x==90 && arena.dummy_x==134 &&
                arena.player_hp==5 && arena.dummy_hp==3 &&
                !demo_active && !demo_complete) {
                const unsigned pitch_px=(unsigned)(stride/sizeof(uint32_t));
                const uint32_t caption=frame[670u*pitch_px+801u];
                const uint32_t impact=frame[335u*pitch_px+465u];
                const uint32_t actor=frame[425u*pitch_px+334u];
                const uint32_t ground=frame[640u*pitch_px+100u];
                if (caption==rgb(91,235,201) &&
                    impact==rgb(255,243,164) &&
                    actor==rgb(62,180,208) &&
                    ground==rgb(62,83,74)) {
                    guest_counter_frame_pixels_valid=true;
                    guest_counter_pixel_caption=caption;
                    guest_counter_pixel_impact=impact;
                    guest_counter_pixel_player=actor;
                    guest_counter_pixel_background=ground;
                    guest_counter_pixel_tick=arena.ticks;
                    guest_counter_pixel_ttl=counter_feedback_ticks;
                    guest_counter_pixel_flash=arena.dummy_impact_flash;
                }
            }
#endif
        } else if (show_scene && scene_rgba) {
            scene_frame(frame,stride/sizeof(uint32_t),scene_rgba,
                        sequence_blob?&sequence:NULL,
                        sequence_blob?&playback:NULL);
#ifdef DINO_SYNTHETIC_SCENE_HOST_VISIBLE_313
            if (synthetic_scene_guest_ready) {
                /* Four-bit optical frame ID plus magenta locator in the
                 * left margin, outside the 3x CPS-1 scene. Host X11 must
                 * observe these from the displayed emulator window.
                 * Optical pixels never contaminate the scene RGBA hash. */
                const unsigned pitch=(unsigned)(stride/sizeof(uint32_t));
                /* Far locator spans the framebuffer width to calibrate
                 * real host viewport scaling with subpixel precision.
                 * Both optical markers are outside the scene rectangle. */
                rectangle(frame,pitch,8,188,18,18,rgb(255,0,255));
                rectangle(frame,pitch,1250,188,18,18,rgb(255,0,255));
                for (unsigned bit=0;bit<4u;++bit)
                    rectangle(frame,pitch,8,214+(int)(bit*26u),18,18,
                              (playback.index&(1u<<bit))
                                  ?rgb(0,255,0):rgb(255,0,0));
            }
#endif
        } else if (gfx)
            viewer_frame(frame,stride/sizeof(uint32_t),page,invert,grid,transparent);
#ifdef DINO_SYNTHETIC_SCENE_GUEST_PROBE
        /* The NRO will only count the frame if it actually drew its
         * 3x-scaled scene into the framebuffer being submitted. Record
         * sampled framebuffer pixels before End, serialize AFTER End. */
        const bool synthetic_guest_frame_ready =
            synthetic_scene_guest_ready && !arena_active && show_scene &&
            playback.index<14u &&
            (synthetic_guest_seen & (1u<<playback.index))==0u;
        const uint64_t synthetic_guest_scene_hash =
            synthetic_guest_frame_ready ?
            synthetic_fnv64(scene_rgba,CPS1_SCENE_RGBA_BYTES) : 0u;
        const uint64_t synthetic_guest_screen_hash =
            synthetic_guest_frame_ready ?
            synthetic_display_sample(frame,stride/sizeof(uint32_t)) : 0u;
#endif
        framebufferEnd(&fb);
#ifdef DINO_SYNTHETIC_SCENE_GUEST_PROBE
        if (synthetic_guest_frame_ready) {
            /* The first row can only be created after a real End call.
             * Preserve an incomplete trace as INCONCLUSIVE, not SUCCESS. */
            FILE *trace=fopen("sdmc:/cadillacs-synthetic-scene-guest.csv",
                              synthetic_guest_rows==0u?"w":"a");
            if (trace) {
                bool ok=true;
                if (synthetic_guest_rows==0u)
                    ok=fputs("event,index,scene_fnv64,screen_fnv64\n",
                              trace)>=0;
                if (ok) ok=fprintf(trace,"FRAME_SUBMITTED,%u,%016llX,%016llX\n",
                    (unsigned)playback.index,
                    (unsigned long long)synthetic_guest_scene_hash,
                    (unsigned long long)synthetic_guest_screen_hash)>=0;
                int closed=fclose(trace);
                if (!ok || closed!=0) break;
                synthetic_guest_seen|=1u<<playback.index;
                ++synthetic_guest_rows;
#ifndef DINO_SYNTHETIC_SCENE_HOST_VISIBLE_313
                if (synthetic_guest_rows==14u) break;
#else
                /* Retain final guest frame 13 until the host verifies its
                 * visible optical ID and independently matching scene pixels.
                 * The host terminates the emulated NRO after acknowledgment;
                 * disappearing immediately after submission is not proof. */
#endif
            }
        }
#endif
#ifdef DINO_EMULATOR_SELFTEST
        /* Stage 253: append only after the actual framebuffer submission.
         * Defer SD serialization until feedback has ended. A missing or
         * overflowing trace cannot claim host/guest frame identity. */
        if (guest_counter_token_frame_valid &&
            !guest_token_trace_written && !guest_token_trace_overflow) {
            if (guest_token_count<DINO_TOKEN_TRACE_CAP) {
                DinoCounterTokenFrame *row=&guest_token_rows[guest_token_count++];
                row->render_iteration=guest_frame_id;
                row->arena_tick=arena.ticks;
                row->feedback_ttl=counter_feedback_ticks;
                row->impact_ttl=arena.dummy_impact_flash;
                row->token=(uint16_t)guest_frame_id;
            } else guest_token_trace_overflow=true;
        }
        if (guest_token_count>0u && !guest_token_trace_written &&
            !guest_counter_token_frame_valid) {
            const char *const token_path=
                "sdmc:/cadillacs-live-counter-frame-tokens.csv";
            if (!guest_token_trace_overflow) {
                FILE *stream=fopen(token_path,"w");
                if (stream) {
                    bool ok=fputs("event,render_iteration,arena_tick,"
                                  "feedback_ttl,impact_ttl,token_u16\n",
                                  stream)>=0;
                    for (unsigned i=0;i<guest_token_count;++i) {
                        const DinoCounterTokenFrame *row=&guest_token_rows[i];
                        if (fprintf(stream,"TOKEN_SUBMITTED,%u,%u,%u,%u,%u\n",
                            (unsigned)row->render_iteration,
                            (unsigned)row->arena_tick,
                            (unsigned)row->feedback_ttl,
                            (unsigned)row->impact_ttl,
                            (unsigned)row->token)<0) ok=false;
                    }
                    const int closed=fclose(stream);
                    if (!ok || closed!=0) (void)remove(token_path);
                }
            }
            guest_token_trace_written=true;
        }
        /* Write only AFTER framebufferEnd. The sampled data originated
         * from the real submitted guest framebuffer for the same frame.
         * This does NOT prove the emulator displayed those pixels. */
        if (guest_counter_frame_pixels_valid &&
            !guest_counter_framebuffer_written) {
            const char *const path=
                "sdmc:/cadillacs-live-counter-framebuffer.csv";
            FILE *pixels=fopen(path,"w");
            if (pixels) {
                const int header=fputs(
                    "event,render_iteration,arena_tick,feedback_ttl,"
                    "impact_ttl,caption_rgba,impact_rgba,player_rgba,"
                    "background_rgba\n",pixels);
                const int body=fprintf(
                    pixels,
                    "SUBMITTED_COUNTER_FRAME,%u,%u,%u,%u,"
                    "%08X,%08X,%08X,%08X\n",
                    (unsigned)guest_frame_id,
                    (unsigned)guest_counter_pixel_tick,
                    (unsigned)guest_counter_pixel_ttl,
                    (unsigned)guest_counter_pixel_flash,
                    (unsigned)guest_counter_pixel_caption,
                    (unsigned)guest_counter_pixel_impact,
                    (unsigned)guest_counter_pixel_player,
                    (unsigned)guest_counter_pixel_background);
                const int closed=fclose(pixels);
                if (header<0 || body<0 || closed!=0)
                    (void)remove(path);
                else
                    guest_counter_framebuffer_written=true;
            }
        }
        if (guest_frame_clock_started && !guest_frame_clock_flushed) {
            /* Use existing clamped game-loop interval, not a new clock read.
             * Includes zero-game-tick iterations; no disk I/O during the
             * 900-tick audio observation. The first and last render frames
             * may contain unobserved simulation ticks. */
            const DinoGuestFrameClockRow clock_row={
                guest_frame_id,(uint32_t)elapsed_ns,
                guest_frame_full_game_ticks,
                guest_ack_tick_count-guest_ack_before_this_frame
            };
            if (!dino_guest_frame_clock_append(&s_guest_frame_clock,clock_row)) {
                guest_frame_clock_started=false; /* no false complete report */
            } else if (guest_frame_clock_done) {
                const char *const path="sdmc:/cadillacs-guest-frame-clock.csv";
                FILE *out=fopen(path,"w");
                if (out) {
                    const bool complete=dino_guest_frame_clock_write_csv(
                        out,&s_guest_frame_clock);
                    const int closed=fclose(out);
                    if (!complete || closed!=0) (void)remove(path);
                }
                guest_frame_clock_flushed=true;
                guest_frame_clock_started=false;
            }
        }
#if defined(DINO_AUDIO_EXPERIMENT_RESUME_RAMP)
        if (guest_resume_report_ready && !guest_resume_report_written) {
            /* Exclusive opt-in guest only; after 900 audio ticks, not
             * in the measured sample-render hot path. */
            const char *const resume_path=
                "sdmc:/cadillacs-guest-resume-ramp.csv";
            FILE *resume_output=fopen(resume_path,"w");
            if (resume_output) {
                const bool start_ok=fputs(
                    "sampled_ticks,applied_start,applied_end,"
                    "full_skips_start,full_skips_end,"
                    "pending_at_start,pending_at_end\n",
                    resume_output)>=0;
                const bool end_ok=fprintf(resume_output,
                    "%u,%u,%u,%u,%u,%u,%u\n",
                    900u,guest_resume_start_count,guest_resume_end_count,
                    guest_resume_start_full,guest_resume_end_full,
                    guest_resume_initial_pending,guest_resume_final_pending)>=0;
                const int closed=fclose(resume_output);
                if (!start_ok || !end_ok || closed!=0)
                    (void)remove(resume_path);
            }
            guest_resume_report_written=true;
        }
#endif
        if (guest_witness && arena_active) {
            if (!guest_first_frame && arena.ticks>0) {
                /* This proves guest code reached framebufferEnd, not
                 * that a host screenshot or visible GPU image exists. */
                guest_report_row(guest_witness,"FRAME_SUBMITTED",
                                 arena.ticks,&arena,demo_witness);
                guest_first_frame=true;
            }
            if (!guest_done && demo_complete) {
                guest_report_row(guest_witness,"REPLAY_DONE",
                                 demo_ticks,&arena,demo_witness);
                guest_done=true;
            }
        }
#endif
    }
#ifdef DINO_EMULATOR_SELFTEST
    if (guest_witness) fclose(guest_witness);
    if (guest_controller_witness) fclose(guest_controller_witness);
    if (guest_hid_timeline) fclose(guest_hid_timeline);
    if (guest_audio_stress) fclose(guest_audio_stress);
#endif
    dino_switch_sound_close();
    framebufferClose(&fb);
    free(scene_rgba);
    free(scene);
    free(sequence_blob);
    free(gfx);
    return 0;
}

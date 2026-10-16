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

enum { FB_WIDTH = 1280, FB_HEIGHT = 720, TILE_SCALE = 4,
       GRID_COLS = 16, GRID_ROWS = 8, PAGE_TILES = GRID_COLS * GRID_ROWS,
       PAGE_COUNT = CPS1_TILE16_COUNT / PAGE_TILES };
static const char *const GFX_PATH =
    "sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin";
static uint8_t s_cache[PAGE_TILES][CPS1_TILE16_PIXELS];
static const char *const SCENE_PATH =
    "sdmc:/switch/cadillacs-dinosaurs-switch/scene.bin";

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

static void scene_frame(uint32_t *frame,unsigned pitch,const uint8_t *rgba) {
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
    label(frame,pitch,64,4,"NATIVE CPS1 SCENE   DPAD PAN   ZR FAST   A RESET",1,rgb(215,226,231));
    label(frame,pitch,64,704,"X TILES   PLUS EXIT   DIAGNOSTIC NOT GAMEPLAY",1,rgb(180,198,206));
}

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

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    padConfigureInput(1,HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    uint8_t *gfx=load_region();
    if (!gfx) { fallback_text(&pad); return 0; }

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
    uint8_t *scene_rgba=load_scene_image(gfx,&scene);
    uint16_t initial_scrollx[3]={0}, initial_scrolly[3]={0};
    if (scene) {
        memcpy(initial_scrollx,scene->scrollx,sizeof(initial_scrollx));
        memcpy(initial_scrolly,scene->scrolly,sizeof(initial_scrolly));
    }
    bool show_scene=false;
    cache_page(gfx,page);
    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 down=padGetButtonsDown(&pad);
        const u64 held=padGetButtons(&pad);
        if (down & HidNpadButton_Plus) break;
        if (show_scene && scene_rgba && scene) {
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
        if (!show_scene && (down & HidNpadButton_Left) && next>0) --next;
        if (!show_scene && (down & HidNpadButton_Right) && next+1<PAGE_COUNT) ++next;
        if (!show_scene && (down & HidNpadButton_Up)) next=next>=16?next-16:0;
        if (!show_scene && (down & HidNpadButton_Down)) next=next+16<PAGE_COUNT?next+16:PAGE_COUNT-1;
        if (!show_scene && (down & HidNpadButton_L)) next=next>=8?next-8:0;
        if (!show_scene && (down & HidNpadButton_R)) next=next+8<PAGE_COUNT?next+8:PAGE_COUNT-1;
        if (!show_scene && (down & HidNpadButton_A)) invert=!invert;
        if (!show_scene && (down & HidNpadButton_B)) transparent=!transparent;
        if (!show_scene && (down & HidNpadButton_Y)) grid=!grid;
        if ((down & HidNpadButton_X) && scene_rgba) show_scene=!show_scene;
        if (next != page && cache_page(gfx,next)) page=next;
        u32 stride=0;
        uint32_t *frame=(uint32_t*)framebufferBegin(&fb,&stride);
        if (!frame) break;
        if (show_scene && scene_rgba)
            scene_frame(frame,stride/sizeof(uint32_t),scene_rgba);
        else
            viewer_frame(frame,stride/sizeof(uint32_t),page,invert,grid,transparent);
        framebufferEnd(&fb);
    }
    framebufferClose(&fb);
    free(scene_rgba);
    free(scene);
    free(gfx);
    return 0;
}

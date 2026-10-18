/* Native desktop smoke renderer and input bridge for an entirely original
 * ROM-free training arena. This is NOT Nintendo Switch emulation.
 * It links the EXACT portable C game and synthesizer used by the NRO.
 */
#include "../source/dino_arena.h"
#include "../source/dino_sfx.h"
#include "../source/dino_replay.h"
#include "../source/dino_replay_witness.h"
#include <stdint.h>
#include <stddef.h>

enum { W=384,H=224,CHANNELS=3 };
static DinoArena game;
static DinoSfx sfx;
static uint64_t pcm_hash;
static uint64_t gameplay_hash;
static const uint64_t FNV_OFFSET=UINT64_C(14695981039346656037);
static const uint64_t FNV_PRIME=UINT64_C(1099511628211);

typedef struct {
    int32_t x,y,z,dummy_x,dummy_y;
    uint32_t ticks,events,successful_hits;
    uint32_t player_pose,enemy_pose,combo;
    uint32_t player_hp,enemy_hp,sparring;
    uint64_t pcm_digest;
    uint64_t gameplay_digest;
} HostArenaStatus;

void dino_host_reset(void) {
    dino_arena_reset(&game);
    dino_sfx_reset(&sfx);
    pcm_hash=FNV_OFFSET;
    gameplay_hash=DINO_WITNESS_INIT;
}
void dino_host_step(uint32_t held,uint32_t pressed) {
    int16_t pcm[DINO_SFX_TICK_FRAMES*2];
    dino_arena_step(&game,held,pressed);
    gameplay_hash=dino_replay_witness_tick(gameplay_hash,&game);
    dino_sfx_events(&sfx,game.events);
    dino_sfx_render_tick(&sfx,pcm,DINO_SFX_TICK_FRAMES);
    /* Hash PCM samples in explicitly defined little-endian order,
     * including silence. No original sound files are accessed. */
    for (unsigned i=0;i<DINO_SFX_TICK_FRAMES*2u;++i) {
        uint16_t v=(uint16_t)pcm[i];
        pcm_hash^=(uint8_t)v;
        pcm_hash*=FNV_PRIME;
        pcm_hash^=(uint8_t)(v>>8);
        pcm_hash*=FNV_PRIME;
    }
}
void dino_host_demo_step(uint32_t tick) {
    uint32_t held=0,pressed=0;
    if (dino_replay_input(tick,&held,&pressed))
        dino_host_step(held,pressed);
}
void dino_host_status(HostArenaStatus *out) {
    if (!out) return;
    *out=(HostArenaStatus){
        .x=game.x,.y=game.y,.z=game.z,
        .dummy_x=game.dummy_x,.dummy_y=game.dummy_y,
        .ticks=game.ticks,.events=game.events,
        .successful_hits=game.successful_hits,
        .player_pose=(uint32_t)dino_arena_player_pose(&game),
        .enemy_pose=(uint32_t)dino_arena_dummy_pose(&game),
        .combo=game.combo_hits,.player_hp=game.player_hp,
        .enemy_hp=game.dummy_hp,.sparring=game.sparring,
        .pcm_digest=pcm_hash,
        .gameplay_digest=gameplay_hash
    };
}
static void rect(uint8_t *buffer,int x,int y,int w,int h,
                 uint8_t r,uint8_t g,uint8_t b) {
    if (x<0) {w+=x;x=0;}
    if (y<0) {h+=y;y=0;}
    if (x>=W || y>=H || w<=0 || h<=0) return;
    if (w>W-x) w=W-x;
    if (h>H-y) h=H-y;
    for (int py=y;py<y+h;++py)
        for (int px=x;px<x+w;++px) {
            size_t pos=(size_t)(py*W+px)*CHANNELS;
            buffer[pos]=r;buffer[pos+1]=g;buffer[pos+2]=b;
        }
}
void dino_host_render(uint8_t *rgb,size_t bytes) {
    if (!rgb || bytes<(size_t)W*H*CHANNELS) return;
    rect(rgb,0,0,W,H,30,61,70);
    rect(rgb,0,80,W,H-80,62,83,74);
    for(int y=80;y<H;y+=16)
        rect(rgb,0,y,W,1,86,108,94);
    const DinoArenaPose enemy=dino_arena_dummy_pose(&game);
    const DinoArenaPose hero=dino_arena_player_pose(&game);
    const int phase=(int)dino_arena_pose_phase(&game);
    const int ex=(int)game.dummy_x,ey=(int)game.dummy_y;
    if (game.dummy_impact_flash) {
        rect(rgb,ex-10,ey-43,20,2,255,243,164);
        rect(rgb,ex-1,ey-49,2,15,255,243,164);
    }
    if (game.finisher_flash) {
        rect(rgb,ex-12,ey-52,24,3,251,221,89);
    }
    if (enemy==DINO_POSE_KO) {
        rect(rgb,ex-12,ey-5,24,4,101,81,66);
    } else {
        int bob=(enemy==DINO_POSE_WALK && phase)?2:0;
        int crouch=(enemy==DINO_POSE_WINDUP)?4:0;
        rect(rgb,ex-6,ey-2,12,2,26,37,40);
        rect(rgb,ex-6,ey-34+bob+crouch,12,30-crouch-bob,
             enemy==DINO_POSE_HURT?247:enemy==DINO_POSE_WINDUP?224:190,
             enemy==DINO_POSE_HURT?196:enemy==DINO_POSE_WINDUP?149:126,
             enemy==DINO_POSE_HURT?120:enemy==DINO_POSE_WINDUP?65:74);
        rect(rgb,ex-4,ey-39+bob+crouch,8,6,231,202,142);
        if (enemy==DINO_POSE_WINDUP) {
            rect(rgb,ex-8,ey-42,1,40,254,224,69);
            rect(rgb,ex+7,ey-42,1,40,254,224,69);
        }
        if(enemy==DINO_POSE_ATTACK)
            rect(rgb,ex+(game.dummy_facing_right?7:-27),ey-24,20,6,
                 246,142,94);
        for(unsigned i=0;i<game.dummy_hp;++i)
            rect(rgb,ex-10+(int)i*7,ey-47,5,2,250,196,87);
    }
    const int px=(int)game.x,py=(int)game.y,rise=(int)game.z;
    rect(rgb,px-6,py-2,12,2,27,39,43);
    if(game.player_impact_flash)
        rect(rgb,px-9,py-rise-39,18,2,255,165,105);
    if(hero==DINO_POSE_KO) {
        rect(rgb,px-12,py-5,24,4,91,112,140);
    } else {
        int bob=(hero==DINO_POSE_WALK&&phase)?2:0;
        rect(rgb,px-5,py-rise-25+bob,10,23-bob,
             hero==DINO_POSE_HURT?251:62,
             hero==DINO_POSE_HURT?121:180,
             hero==DINO_POSE_HURT?106:208);
        rect(rgb,px-4,py-rise-31+bob,8,6,231,218,164);
        if(hero==DINO_POSE_ATTACK)
            rect(rgb,px+(game.facing_right?6:-26),py-rise-21,20,6,
                 249,214,100);
    }
}

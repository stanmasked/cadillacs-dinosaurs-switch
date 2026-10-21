/* ROM-free stress of the invented Switch training arena, not Capcom gameplay.
 * stdin: exactly one nominal active-low P1 byte per private 0.106 INP record.
 * Never publish the input sequence, original game data or private receipts.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "dino_arena.h"
static uint32_t mapping(uint8_t v) {
    uint32_t h=0;
    if (!(v&0x01u)) h|=DINO_ARENA_RIGHT;
    if (!(v&0x02u)) h|=DINO_ARENA_LEFT;
    if (!(v&0x04u)) h|=DINO_ARENA_DOWN;
    if (!(v&0x08u)) h|=DINO_ARENA_UP;
    if (!(v&0x10u)) h|=DINO_ARENA_ATTACK;
    if (!(v&0x20u)) h|=DINO_ARENA_JUMP;
    return h;
}
static uint64_t mix(uint64_t hash,uint32_t value) {
    for(int byte=0;byte<4;byte++) {
        hash^=(uint8_t)(value>>(8*byte));
        hash*=UINT64_C(1099511628211);
    }
    return hash;
}
static int hex_digit(char x) {
    if(x>='0' && x<='9') return x-'0';
    if(x>='a' && x<='f') return x-'a'+10;
    if(x>='A' && x<='F') return x-'A'+10;
    return -1;
}
/* Stage277: portable, canonical hash of all simulation fields;
 * no compiler-dependent struct padding, no original ROM contents. */
static uint64_t mix_full_state(uint64_t h,const DinoArena *a) {
    const uint32_t words[]={
        (uint32_t)a->x,(uint32_t)a->y,(uint32_t)a->z,(uint32_t)a->vz,
        (uint32_t)a->dummy_x,(uint32_t)a->dummy_y,
        (uint32_t)a->ticks,(uint32_t)a->successful_hits,
        (uint32_t)a->facing_right,(uint32_t)a->dummy_hp,
        (uint32_t)a->dummy_hitstun,(uint32_t)a->attack_frames,
        (uint32_t)a->attack_cooldown,(uint32_t)a->sparring,
        (uint32_t)a->player_hp,(uint32_t)a->player_hitstun,
        (uint32_t)a->player_invuln,(uint32_t)a->dummy_windup,
        (uint32_t)a->dummy_cooldown,(uint32_t)a->dummy_attack_frames,
        (uint32_t)a->dummy_facing_right,(uint32_t)a->player_hits_taken,
        (uint32_t)a->player_moving,(uint32_t)a->dummy_moving,
        (uint32_t)a->combo_hits,(uint32_t)a->combo_timer,
        (uint32_t)a->finisher_flash,(uint32_t)a->dummy_impact_flash,
        (uint32_t)a->player_impact_flash,(uint32_t)a->events
    };
    for(size_t i=0;i<sizeof(words)/sizeof(words[0]);i++) h=mix(h,words[i]);
    return h;
}
int main(int argc,char **argv) {
    int spar=0,seen_prior=0;
    uint8_t prior=255u;
    for(int a=1;a<argc;a++) {
        const char *prefix="--prior-active-low=";
        const size_t length=strlen(prefix);
        if(!strcmp(argv[a],"--spar") && !spar) {
            spar=1;
        } else if(!seen_prior && !strncmp(argv[a],prefix,length) &&
                  strlen(argv[a]+length)==2u &&
                  hex_digit(argv[a][length])>=0 &&
                  hex_digit(argv[a][length+1])>=0) {
            prior=(uint8_t)(hex_digit(argv[a][length])*16+
                            hex_digit(argv[a][length+1]));
            seen_prior=1;
        } else {
            fputs("usage: arena_stress [--spar] [--prior-active-low=HH]\n",stderr);
            return 2;
        }
    }
    DinoArena arena;
    dino_arena_reset(&arena);
    if(spar) dino_arena_step(&arena,0,DINO_ARENA_TOGGLE_SPAR);
    uint32_t previous=mapping(prior),frames=0,presses_attack=0,presses_jump=0;
    uint32_t live_attacks=0,live_jumps=0;
    uint64_t digest=UINT64_C(14695981039346656037);
    uint64_t full_state_digest=UINT64_C(14695981039346656037);
    unsigned char input[32768];
    for(;;) {
        size_t n=fread(input,1,sizeof(input),stdin);
        if(!n) break;
        for(size_t i=0;i<n;i++) {
            if(frames>=UINT32_C(10000000)) {fputs("input too long\n",stderr);return 2;}
            uint32_t held=mapping(input[i]);
            uint32_t pressed=held&~previous&(DINO_ARENA_ATTACK|DINO_ARENA_JUMP);
            previous=held;
            presses_attack+=(pressed&DINO_ARENA_ATTACK)!=0;
            presses_jump+=(pressed&DINO_ARENA_JUMP)!=0;
            dino_arena_step(&arena,held,pressed);
            live_attacks+=(arena.events&DINO_EVT_PLAYER_SWING)!=0;
            live_jumps+=(arena.events&DINO_EVT_JUMP_START)!=0;
            if(arena.x<16 || arena.x>DINO_ARENA_WIDTH-16 ||
               arena.y<80 || arena.y>DINO_ARENA_HEIGHT-16 ||
               arena.z<0 || arena.player_hp>5 || arena.dummy_hp>3) {
                fputs("arena invariant violated\n",stderr);return 3;
            }
            digest=mix(digest,arena.ticks);
            digest=mix(digest,(uint32_t)arena.x);
            digest=mix(digest,(uint32_t)arena.y);
            digest=mix(digest,(uint32_t)arena.z);
            digest=mix(digest,(uint32_t)arena.successful_hits);
            digest=mix(digest,(uint32_t)arena.events);
            full_state_digest=mix_full_state(full_state_digest,&arena);
            frames++;
        }
        if(n<sizeof(input)) {
            if(ferror(stdin)) {fputs("stdin read error\n",stderr);return 3;}
            break;
        }
    }
    if(!frames || arena.ticks!=frames+(unsigned)spar) {
        fputs("empty or inconsistent simulated frame count\n",stderr);return 3;
    }
    printf("{\"schema\":\"dino-original-arena-private-input-stress-v1\","
           "\"training_only\":true,\"wolfmame_playback_verified\":false,"
           "\"original_gameplay_parity_verified\":false,"
           "\"sparring_mode\":%s,\"nominal_input_records\":%u,"
           "\"attack_press_edges\":%u,\"jump_press_edges\":%u,"
           "\"actual_training_swings\":%u,\"actual_training_jumps\":%u,"
           "\"player_hp\":%u,\"target_hp\":%u,"
           "\"successful_training_hits\":%u,\"player_hits_taken\":%u,"
           "\"state_digest_fnv64\":\"%016llx\",\"full_state_digest_fnv64\":\"%016llx\",\"full_state_fields\":30}\n",
           spar?"true":"false",frames,presses_attack,presses_jump,
           live_attacks,live_jumps,arena.player_hp,arena.dummy_hp,
           arena.successful_hits,arena.player_hits_taken,
           (unsigned long long)digest,(unsigned long long)full_state_digest);
    return 0;
}

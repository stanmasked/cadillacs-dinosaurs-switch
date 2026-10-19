#include "dino_guest_counter_probe.h"
#include "dino_arena.h"
#include "dino_sfx.h"
#include <stdint.h>

/* Executed inside the real ARM64 guest in DINO_EMULATOR_SELFTEST builds.
 * It is NOT a controller test. The real 180-tick replay and gameplay
 * arena continue independently; this owns only local diagnostic state.
 * No ROM/game art/sound file is read, and no synthetic input is
 * substituted for libnx HID evidence.
 */
static int record(FILE *out, const char *phase, const DinoArena *a,
                  unsigned pcm_nonzero) {
    return fprintf(out,"%s,%u,%u,%u,%u,%u,%u,%u,%u\n",
                   phase,(unsigned)a->ticks,(unsigned)a->player_hp,
                   (unsigned)a->dummy_hp,(unsigned)a->dummy_windup,
                   (unsigned)a->dummy_hitstun,(unsigned)a->dummy_cooldown,
                   (unsigned)a->events,pcm_nonzero)>0;
}

int dino_guest_counter_probe(FILE *out) {
    if (!out) return 0;
    DinoArena a;
    DinoSfx synth;
    int16_t pcm[DINO_SFX_TICK_FRAMES*2u];
    unsigned nonzero=0u;
    dino_arena_reset(&a);
    if (fputs("phase,tick,player_hp,enemy_hp,windup,stun,cooldown,"
              "event_mask,pcm_nonzero\n",out)<0 ||
        !record(out,"RESET",&a,0u)) return 0;

    /* Same player position and button edges as the original host tests. */
    a.x=220;
    dino_arena_step(&a,0u,DINO_ARENA_TOGGLE_SPAR);
    if (!record(out,"ARMED",&a,0u)) return 0;
    dino_arena_step(&a,0u,DINO_ARENA_COUNTER);
    dino_sfx_reset(&synth);
    dino_sfx_events(&synth,a.events);
    dino_sfx_render_tick(&synth,pcm,DINO_SFX_TICK_FRAMES);
    for (unsigned i=0u;i<2u*DINO_SFX_TICK_FRAMES;++i)
        if (pcm[i]!=0) { nonzero=1u; break; }
    if (!record(out,"COUNTER",&a,nonzero)) return 0;
    dino_arena_step(&a,0u,0u);
    if (!record(out,"RECOVERY",&a,0u)) return 0;

    /* Negative control: facing away on last windup tick must take the
     * ordinary hit; counter must never provide passive invulnerability. */
    dino_arena_reset(&a);
    a.x=220;
    dino_arena_step(&a,0u,DINO_ARENA_TOGGLE_SPAR);
    a.facing_right=0u;
    a.dummy_windup=1u;
    dino_arena_step(&a,0u,DINO_ARENA_COUNTER);
    if (!record(out,"WRONG_FACING",&a,0u)) return 0;
    return !ferror(out);
}

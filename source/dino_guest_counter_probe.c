#include "dino_guest_counter_probe.h"
#include "dino_arena.h"
#include "dino_sfx.h"
#include "dino_pcm_witness.h"
#include <stdint.h>

/* Executed inside the real ARM64 guest in DINO_EMULATOR_SELFTEST builds.
 * It is NOT a controller test. The real 180-tick replay and gameplay
 * arena continue independently; this owns only local diagnostic state.
 * No ROM/game art/sound file is read, and no synthetic input is
 * substituted for libnx HID evidence.
 */
static int record(FILE *out, const char *phase, const DinoArena *a,
                  unsigned pcm_nonzero, uint64_t pcm_hash) {
    return fprintf(out,"%s,%u,%u,%u,%u,%u,%u,%u,%u,%016llX\n",
                   phase,(unsigned)a->ticks,(unsigned)a->player_hp,
                   (unsigned)a->dummy_hp,(unsigned)a->dummy_windup,
                   (unsigned)a->dummy_hitstun,(unsigned)a->dummy_cooldown,
                   (unsigned)a->events,pcm_nonzero,
                   (unsigned long long)pcm_hash)>0;
}

/* Probe illegal presses on the EXACT impact tick, where an accidental
 * last-tick countdown/landing eligibility bug could grant free defense.
 * The scripted counter edge must not cancel the enemy swing or damage.
 * Diagnostic PCM is intentionally not rendered for these negative rows. */
static int boundary_case(FILE *out, const char *phase, unsigned scenario) {
    DinoArena a;
    uint32_t pressed=DINO_ARENA_COUNTER;
    dino_arena_reset(&a);
    a.x=220;
    dino_arena_step(&a,0u,DINO_ARENA_TOGGLE_SPAR);
    a.dummy_windup=1u;
    switch (scenario) {
    case 0u: a.player_hitstun=1u; break;
    case 1u: a.attack_frames=1u; break;
    case 2u: a.z=1; a.vz=-2; break;
    case 3u:
        a.attack_cooldown=10u;
        pressed|=DINO_ARENA_ATTACK;
        break;
    case 4u: pressed|=DINO_ARENA_JUMP; break;
    default: return 0;
    }
    dino_arena_step(&a,0u,pressed);
    return record(out,phase,&a,0u,DINO_PCM_WITNESS_INIT);
}

int dino_guest_counter_probe(FILE *out) {
    if (!out) return 0;
    DinoArena a;
    DinoSfx synth;
    int16_t pcm[DINO_SFX_TICK_FRAMES*2u];
    unsigned nonzero=0u;
    dino_arena_reset(&a);
    if (fputs("phase,tick,player_hp,enemy_hp,windup,stun,cooldown,"
              "event_mask,pcm_nonzero,pcm_fnv64\n",out)<0 ||
        !record(out,"RESET",&a,0u,DINO_PCM_WITNESS_INIT)) return 0;

    /* Same player position and button edges as the original host tests. */
    a.x=220;
    dino_arena_step(&a,0u,DINO_ARENA_TOGGLE_SPAR);
    if (!record(out,"ARMED",&a,0u,DINO_PCM_WITNESS_INIT)) return 0;
    dino_arena_step(&a,0u,DINO_ARENA_COUNTER);
    dino_sfx_reset(&synth);
    dino_sfx_events(&synth,a.events);
    dino_sfx_render_tick(&synth,pcm,DINO_SFX_TICK_FRAMES);
    for (unsigned i=0u;i<2u*DINO_SFX_TICK_FRAMES;++i)
        if (pcm[i]!=0) { nonzero=1u; break; }
    /* Hash all 1600 interleaved int16 samples in explicit little-endian
     * byte order, independent of the guest CPU architecture. */
    const uint64_t counter_pcm_hash=dino_pcm_witness_feed(
        DINO_PCM_WITNESS_INIT,pcm,DINO_SFX_TICK_FRAMES);
    if (!record(out,"COUNTER",&a,nonzero,counter_pcm_hash)) return 0;
    dino_arena_step(&a,0u,0u);
    if (!record(out,"RECOVERY",&a,0u,DINO_PCM_WITNESS_INIT)) return 0;

    /* A repeated counter edge while the opponent is stunned and its
     * recovery timer is nonzero must do nothing, without invulnerability.
     * It is a scripted test press; the UI still requires a true key edge. */
    dino_arena_step(&a,0u,DINO_ARENA_COUNTER);
    if (!record(out,"EARLY_REPEAT",&a,0u,DINO_PCM_WITNESS_INIT)) return 0;

    /* 46 later 60-Hz ticks exactly finish the remaining cooldown.
     * The opponent may start its next 12-tick telegraph, but the
     * player cannot have received a hit during those recovery ticks. */
    for (unsigned tick=0u;tick<46u;++tick) dino_arena_step(&a,0u,0u);
    if (!record(out,"REARMED",&a,0u,DINO_PCM_WITNESS_INIT)) return 0;

    /* A NEW edge at the NEXT tick can interrupt the new telegraph.
     * Re-run the exact original synthesized cue in an isolated synth
     * to require byte-stable PCM for two separately legal counters. */
    dino_arena_step(&a,0u,DINO_ARENA_COUNTER);
    dino_sfx_reset(&synth);
    dino_sfx_events(&synth,a.events);
    dino_sfx_render_tick(&synth,pcm,DINO_SFX_TICK_FRAMES);
    nonzero=0u;
    for (unsigned i=0u;i<2u*DINO_SFX_TICK_FRAMES;++i)
        if (pcm[i]!=0) { nonzero=1u; break; }
    const uint64_t second_pcm_hash=dino_pcm_witness_feed(
        DINO_PCM_WITNESS_INIT,pcm,DINO_SFX_TICK_FRAMES);
    if (!record(out,"SECOND_COUNTER",&a,nonzero,second_pcm_hash)) return 0;

    /* Negative control: facing away on last windup tick must take the
     * ordinary hit; counter must never provide passive invulnerability. */
    dino_arena_reset(&a);
    a.x=220;
    dino_arena_step(&a,0u,DINO_ARENA_TOGGLE_SPAR);
    a.facing_right=0u;
    a.dummy_windup=1u;
    dino_arena_step(&a,0u,DINO_ARENA_COUNTER);
    if (!record(out,"WRONG_FACING",&a,0u,DINO_PCM_WITNESS_INIT)) return 0;

    /* All five cases must reject counter even though windup expires
     * THIS SAME tick. The actual enemy impact still resolves normally. */
    if (!boundary_case(out,"LAST_HITSTUN",0u) ||
        !boundary_case(out,"LAST_ATTACK",1u) ||
        !boundary_case(out,"LANDING",2u) ||
        !boundary_case(out,"ATTACK_CHORD",3u) ||
        !boundary_case(out,"JUMP_CHORD",4u)) return 0;
    return !ferror(out);
}

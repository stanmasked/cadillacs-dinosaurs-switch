# Switch ROM-free arena — stage 114

This is a **playable, entirely original technical training-room prototype**
integrated into the same native Nintendo Switch NRO as the CPS-1 tile/scene
inspector. **It is not Cadillacs and Dinosaurs gameplay or an arcade emulator.**

## What is running

- Deterministic fixed-step **60 Hz** update in portable `source/dino_arena.c`.
- Single controllable, geometrically drawn placeholder actor, fixed camera
  and a stationary 3-HP training dummy.
- Horizontal and lane-depth movement, left/right facing, one jump arc,
  attack range checks, a single-hit attack event, attack cooldown,
  health decrement and training-room reset.
- All arithmetic is bounded, integer-only, and has no heap, ROM, assets,
  filesystem, audio or Switch dependencies in the core simulation module.
- The main NRO draws a 384×224 original sandbox at 3× integer scale with
  simple rectangles and an ASCII HUD; no game sprites or palettes are used.

It deliberately **does not** implement original controls, four selectable
characters, enemy AI, stages, genuine attack animations, CPS-1 physics,
cooperative play, music, SFX, scripted events, weapons or HD graphics.

## Launch and controls

Build using devkitPro `switch-dev` and copy the NRO to your own Switch
homebrew SD location. If
`sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin` is **absent**, the NRO
starts directly in the original training room. It no longer needs
commercial ROM graphics merely to display and control the prototype.

If that file **is** present, the established diagnostic tile/scene mode
remains the default. Press **ZL** to toggle between the training room
and the current tile/scene viewer. No original game asset is generated
or installed by this feature.

| Control | Training-room action |
| --- | --- |
| D-pad Left / Right | Move and face left/right |
| D-pad Up / Down | Move within the depth lane |
| A | One attack (subject to cooldown) |
| B | Jump (no mid-air restart) |
| Y | Reset player and training dummy |
| ZL | Toggle viewer/training room (only when `gfx.bin` exists) |
| + | Exit |

The dummy is stationary and takes at most one hit per attack event,
not continuous damage during the visible attack effect. Once defeated,
it stays inactive until reset. Jumping above a short vertical height
prevents attacking a ground-level dummy.

## Verification and limits

`tests/test_dino_arena.py` compiles the exact portable C simulation
used in the NRO into a Linux shared library and drives it via ctypes
with **fabricated, ROM-free state only**. The twelve regressions cover
movement bounds, diagonal/contradictory inputs, ground/jump physics,
facing/range/lane conditions, cooldown, health depletion/reset,
high-jump attack refusal and deterministic 300-tick replay.

Run locally:

```sh
python3 -m unittest discover -s tests -v
```

Then run the ordinary `make` with devkitPro installed.
GitHub Actions builds and tests only ROM-free source and synthesized
test fixtures; it does not run gameplay on a real Switch. Native NRO
compilation is **not proof of successful execution on physical hardware**.

This is a separate scaffold for building eventual mechanics.
It does **not** reproduce an original MAME gameplay frame, resolve
the original `ioc1.ic1`/QSound ROM dependencies, validate audio or
determine likeness to Capcom's original gameplay. Real game-faithful
mechanics require independently verified references and appropriate
rights for distributing protected characters, story and artwork.

## Stage 115 — opt-in sparring against an invented training opponent

Press **X** in the arena to toggle **SPAR ON/OFF**. The default after
reset is still the stationary three-HP dummy; the earlier target-practice
controls, test outcomes and tile/scene viewer remain available.

With sparring enabled, the opponent now moves deterministically
towards the player at a bounded integer rate, changes depth lanes
to follow the player, respects same-lane body separation, and has
a visible **12-tick attack windup** followed by one damage check.
The attack has a 48-tick cooldown and a short visible follow-through.
Players begin sparring with five HP and receive 30 ticks of
post-hit invulnerability. Attacking first interrupts an opponent
windup, and leaving the depth lane, moving out of range or jumping
above the strike height can evade a telegraphed hit. The player
cannot initiate new actions after zero HP; a defeated opponent
cannot deliver new hits.

The new fields are confined to `DinoArena` in
`source/dino_arena.h` and `source/dino_arena.c`; the 60 Hz
simulation remains portable C and doesn't read or decode ROM
graphics. The Switch UI draws the invented opponent's windup
outline, attack flash and two HP counters using plain shapes.
Press **Y** to reset the training session; press **X** to turn
sparring off again.

The expanded `tests/test_dino_arena.py` uses host-compiled C
and synthetic inputs to cover: explicit opt-in, opponent pursuit,
body blocking, passing from another depth lane, telegraph latency,
damage and invulnerability, two distinct dodges, hit interruption,
player KO, enemy KO and deterministic 700-tick replay.
This is **not original CPS-1 enemy AI or gameplay physics**;
the values, colors, dummy and attack behavior were invented for
this test harness. No original assets or game runtime have been
captured, distributed or executed as part of this prototype.

## Stage 116 — deterministic pose-state presentation without game assets

The ROM-free arena now exposes read-only C pose queries:
`dino_arena_player_pose()`, `dino_arena_dummy_pose()`, and
`dino_arena_pose_phase()`. Both actors use a deliberately invented
priority order: **knockout > hurt > attack > jump > walk > idle**
for the player, with the enemy's **windup** inserted before attack.
A standing or blocked player does not appear to walk merely because
a direction button is held: each 60 Hz tick records actual movement
of both actors. The opponent's attack preparation has its own
state and a visible warning, while an injured actor displays a
hit reaction until its stun expires.

The two visual phases cycle every six simulation ticks, not according
to the display frame rate. Pose queries do not advance the clock,
mutate physics, consume player input, change hitboxes or allocate
memory. The Switch NRO draws these states with independently designed
geometric rectangles: a walking bob, jump elevation, attack reach,
stun colors, sparring windup and collapsed knockout silhouettes.
The HUD prints the current player/opponent poses and health.
No protected original characters, sprites or original game
animation timings are encoded here.

Nine ROM-free host-C regressions check idle/null behavior,
actual displacement versus blocked input, jump/attack priority,
chase/windup/strike transitions, hurt precedence, knockout
precedence, six-tick visual phase timing, read-only pose queries
and movement reset during stun/KO. These complement the existing
722 synthetic tests; independent CI determines whether the
expanded suite passes.

**Limitations:** these visuals are temporary art-free placeholding.
The game still lacks original fighting system, characters, level
assets, sound and verified actual console execution. Correct
synthetic pose states do not imply MAME-original gameplay parity.

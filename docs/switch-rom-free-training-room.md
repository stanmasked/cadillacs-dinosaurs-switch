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

## Stage 117 — three-hit chain and bounded sparring knockback

The original, asset-free training sandbox now has a **three-hit
combo counter**, not based on any CPS-1 gameplay or move data.
Each distinct confirmed hit may advance the counter from 1 to 3
if the next hit lands within **24 simulation ticks** of the
previous one. Each hit also refreshes that 24-tick window.
A miss or an attack button press during cooldown never advances
or refreshes the combo; a timer expiry, switching sparring mode,
or actually receiving damage clears it.

The **third consecutive landed attack** has a short 10-tick
finisher highlight and lengthens the dummy's stun from 9 to
14 ticks. In optional sparring mode it **knocks the dummy 18
world pixels** in the direction the player is facing, clamped
to the training arena's horizontal bounds (16–368). The stationary
practice dummy deliberately does not shift position when
sparring is disabled, so earlier target-practice exercises still
behave as expected. A fourth hit inside the same chain does not
re-trigger the one-time third-hit finisher. A successful finisher
also updates the opponent-displacement flag for presentation.

The Nintendo Switch NRO displays the current **COMBO 0–3/3**
state beside the two actors' pose/health and highlights the
target briefly after a finisher. All effects use independently
drawn rectangles; they do not contain copied arcade animations,
character likenesses, original combat parameters or hitboxes.

Twelve additional ROM-free C regression methods check exact timer
expiry, misses, cooldown input rejection, three successful hits,
left/right knockback, screen-edge clamping, fourth-hit behavior,
stationary-mode preservation, mode resets, player-damage combo
interruption, short finisher highlight expiration and identical
results after a 1,000-tick deterministic replay.

This stage does **not** reproduce the original Cadillacs and
Dinosaurs combo system. It is an invented training mechanic
and is not proof of original gameplay, original animations,
physical Switch runtime, audio or MAME framebuffer parity.

## Stage 118 — exact one-tick event signals and impact feedback

The invented training-room simulation now records a **one-tick combat
event bitmask** in `DinoArena.events`. It resets at the beginning of
each fixed 60 Hz step, then sets zero or more independent flags for:

- Sparring mode switch; jump start; actual landing
- Started player attack; *confirmed* dummy hit; third-hit finisher;
  first dummy knockout
- Released opponent attack; actual player damage; first player
  knockout; completed opponent swing that was dodged/blocked

An attack input during cooldown **never** produces a new swing event.
A whiff creates a swing event but never a hit. The three-hit
finisher may share a single tick with a dummy-hit and KO event;
only the actual health transition produces the KO event.
A completed opponent windup emits precisely one swing and
either a player-hit event or a dodge/no-damage event. Mode toggle
events do not retain previously reported combat events.
These flags represent only **this tick**, not a buffered event
queue and not original CPS-1 sound or effect timings.

The core keeps separate, fixed-duration graphical feedback:
`dummy_impact_flash` (6 ticks) and
`player_impact_flash` (8 ticks). The homebrew NRO renders
small newly designed geometric sparks next to the actor who
was hit. They remain visible across presentation frames even
though the event bitmask is cleared on the next simulation tick.
The public implementation includes **no arcade audio**, no
ROM-derived sound sequences, original sprites or game states.

Eleven new host-C regressions check exact event boundaries,
jump takeoff and one landing, whiffs and cooldown, landed hits,
third-hit finisher + KO co-occurrence, sparring toggle reset,
opponent attack and damage, last-moment jump dodge, player KO
only once, opponent KO without an automatic finisher, spark
timer expiry and deterministic 500-tick event replay.
Prior stage 117 passed 743 tests; this addition brings the
expected total to **754**, subject to GitHub Actions.

This event vocabulary is an original scaffolding for future
independently authored video/audio effects; it is not proof
of original game hit timings, game audio, MAME execution or
physical Nintendo Switch runtime.

## Stage 119 — original procedural battle sounds (optional)

This ROM-free research NRO now includes independent, newly authored
**procedural sound cues** for all eleven training-combat events.
`source/dino_sfx.c` synthesizes six bounded simultaneous voices with
integer-only triangle or noise waveforms. Per-voice pitch, duration,
amplitude, stereo pan, and relative priority are fixed constants
written for this prototype—not recordings, SPC/QSound samples,
Capcom musical phrases or MAME audio data.

A sample block is **800 stereo frames at 48,000 Hz**, exactly one
60 Hz simulation tick. A sample counter and fixed-duration envelope
make playback independent of rendering frequency; generated buffers
are **signed 16-bit interleaved stereo**, with explicit saturation
and no malloc, file I/O or device-specific calls in the synth.
Each tick consumes that tick's `DinoArena.events` flags.
The six-voice capacity uses deterministic priority replacement:
hits, finishers and KOs override low-priority movement cues under
simultaneous-event load.

The separate `source/dino_switch_sound.c` adapter uses libnx
`audout` only if the operating system provides the documented
48 kHz, two-channel, signed-16-bit audio configuration. It maintains
**four 4096-byte-aligned audio pages**, submits at most one 800-frame
block per simulated tick, and reuses a page only after libnx reports
its release. If audio initialization, buffer submission or retrieval
fails, it closes the sound service and continues the arena silently.
If all buffers are busy, the synth still advances the missed tick
into a private discard buffer rather than blocking the game loop.
The NRO attempts sound initialization only after its framebuffer
has been set up, and always closes the audio service on ordinary
program exit.

The host test suite compiles the **same C synth** into a Linux
shared library via GCC, with no ROM or Switch toolchain required.
Twelve additional tests cover all eleven event identities,
deterministic PCM (including pseudorandom noise), stereo panning,
silence, voice caps/priority, envelope expiry, 16-bit bounds,
unknown flags, reset, invalid frame length, partial frames and
null-pointer safety.

**Unverified until an on-console run:** actual speaker/headphone
audibility, latency, underrun frequency and device behavior.
The GitHub NRO job verifies compilation, not physical playback.
The prototype has no Capcom QSound audio, soundtrack, original
sound effects, original sound timing or licensed samples.

### Listening on a computer without a Switch or ROM

Use the optional host preview tool to generate a local WAV containing
all **eleven newly authored cue sounds** in sequence, separated by
brief silence:

```sh
python3 tools/dino_sfx_preview.py --out /your/private/folder/dino-training-effects.wav
```

A host **GCC** installation is required. The tool compiles the exact
portable C synthesizer under an ephemeral temporary directory and writes
a standard **48 kHz, 16-bit, stereo WAV**. It does not ship prerecorded
commercial sound, nor does it load any existing WAV or ROM. The output
path must be given explicitly, its directory must exist, and an
existing file will **never be overwritten**.

Two additional ROM-free tests independently verify WAV header
dimensions and sample count, byte-for-byte reproducibility, agreement
with the sound engine's direct PCM output, and the no-overwrite rule.
The expanded expected full test count is **768**, subject to CI.

## Stage 120 — bounded audio queue and host-tested release safety

The native libnx `audout` adapter now routes its output-buffer
lifetime decisions through a small platform-independent policy in
`source/dino_audio_queue.c`.

The adapter still owns **four independent, page-aligned 4096-byte**
PCM memory buffers, but it may have **at most two 800-frame blocks**
submitted to the service simultaneously. This corresponds to **no
more than 1600 frames (33.3 ms) of PCM submitted**; it is *not a
measurement of real-world latency or the hardware mixer*. If the
audio device stalls or rendering runs several simulation ticks at
once, no further PCM pages are submitted until an earlier buffer
has been released. The sound synthesizer keeps advancing its
envelopes into a private discard buffer each tick so the game
simulation never waits for audio and never catches up later by
playing stale impact sounds.

A buffer becomes writable again **only** after libnx returns its
exact `AudioOutBuffer*` and the queue finds that buffer
outstanding. Foreign pointers, duplicate releases and audio API
failures cause the adapter to stop the service and fall back to
silence, rather than possibly rewriting a page that the device
is still reading. The independent queue maintains bounded
admission, rejected release/submit checks and counters
(`submitted`, `released`, `skipped`) without allocating memory.

Ten host-native ROM-free tests drive the exact queue C code
against full stalls, invalid indices, duplicate acknowledgments,
out-of-order release, cap enforcement, re-use after release,
state reset, null inputs and an 800-tick repeatability trace.
The privacy and Switch build checks run on the same branch.

This stage does **not** confirm practical audio latency,
sound output or buffer return behavior on physical hardware.
All game sounds remain original synthetic PCM; no MAME/Capcom
audio has been used.

Stage 120 follow-up: repeated attempts to open an already initialized
audio service no longer reset the active synthesized envelopes.
Because `audoutGetReleasedAudioOutBuffer` returns only a single
buffer pointer per call, a reported count other than exactly one
for a nonempty release is now treated as ambiguous and fails
closed to silent operation. This is an added conservative adapter
guard; it does not claim real device behavior has been observed.

The console audio service is now opened **only while the ROM-free
training arena is active**, not during the CPS-1 tile/scene viewer.
Leaving the arena via ZL stops audout and discards pending cue
state; re-entering starts a fresh synth timeline. Three compile-time
assertions ensure that the number of backend slots matches the
portable policy and that one 800-frame stereo block fits in the
aligned audio page. No claims are made about physical Switch
switching latency or actual audible playback.

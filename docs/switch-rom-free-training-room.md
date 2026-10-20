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

## Stage 121 — diagnostic audio-health overlay for physical Switch testing

The ROM-free homebrew training arena now shows a compact technical
audio line above the combat HUD:

`AUDIO ON/OFF/INVALID · QUEUED n/2 · SENT · RELEASED · SKIPPED · ERRORS`

These are **logical PCM block counters**, not measured audio
latency, underrun rate, sound quality or proof that speakers
produced sound. `ON` means libnx's audio-output start call
succeeded; `OFF` indicates the service is not currently
running. `SKIPPED` increments when the service cannot accept
another 800-frame block. `ERRORS` records failures during
audio initialization, submission or buffer-release handling.
After closing the audio service, queue-specific counters reset
because their underlying session is over, while the error counter
is retained so the status display can still flag the failure.

The independent queue exposes a new read-only diagnostic snapshot.
It checks that every busy flag is Boolean, the number of busy
buffers matches the queued count, the two-block cap holds, and
the modular submitted-minus-released count agrees with the
pending count. Inconsistent state returns failure **without
changing the output** or the queue; the Switch UI then shows
`INVALID` instead of a fictitious healthy queue.

Four additional host-native ROM-free regression methods check
snapshot counting across submit/acknowledge/skip, read-only
behavior, refusal of contradictory/injected queue states, and
null-pointer safety. This stage does not depend on original ROM
assets or arcade sound sources.

**Still required for actual device validation:** launch the NRO
on an authorized Switch homebrew device, listen to the synthetic
effects and inspect the on-device audio line for dropped buffers
or audio-service errors. No physical device execution or real
headphone output has been verified by these host tests.

## Stage 225 — timed defensive counter during invented sparring

The optional **SPAR ON** mode gains an original defensive counter move,
implemented directly in the existing ROM-free 60-Hz C arena
(`source/dino_arena.[ch]`). This is **not** an arcade-game mechanic
reconstructed from Capcom's original code or assets.

Press **ZR** once in the Switch training room, or **H** in the native
desktop host preview, **during the opponent's visible 12-tick attack
windup**. The counter succeeds only if the player is alive, on the
ground, not currently hit-stunned or attacking, in the enemy's depth
lane, within 44 world pixels, and facing the enemy. It cannot be
combined with jump or attack in the same simulation tick.

A successful counter interrupts the opponent's winding attack,
applies nine ticks of opponent hit-stun and its existing 48-tick
attack cooldown, and briefly displays **COUNTER!** in the Switch
frame. It does **not** damage the opponent, give the player immunity,
add health, advance combos, or move characters through colliders.
A missed or incorrectly faced counter gives no defense; the ordinary
telegraphed hit and dodge rules still apply.

The counter uses a single press edge (`DINO_ARENA_COUNTER`) and emits
a new one-tick event (`DINO_EVT_COUNTER`). It does not allocate a
timer, introduce a gameplay-state field or change `DinoArena` layout.
The input is never present in the existing automatic 180-tick demo;
all existing replay input sequences, hashes, default camera/game
visuals, source assets and music are unchanged.

The host compiler-based regression suite
`tests/test_dino_arena_counter.py` tests the actual game C module:
successful interrupt, cooldown, attack timing, facing, lane and range,
groundedness, player/enemy KO, simultaneous inputs, controller
toggle path, determinism under legacy replay and a 2,800-tick
bounded random-input challenge. Switch ZR and desktop H routes are
explicitly tested as input edges.

No original ROM or sound assets are required and no claim is made
that this synthetic training counter resembles the arcade original.

## Stage 226 — strict counter input timing at 60 Hz boundaries

The original Stage 225 ZR/H counter is now gated using the **player state
at the beginning of the simulation tick**, before animation/hit-stun
countdowns or gravity are advanced. A counter press on the final tick
of player hit-stun, the final frame of an existing attack animation,
or the tick on which the player lands cannot produce a counter.
Pressing again on the **following eligible tick** can succeed, provided
the opponent is still telegraphing, the distance/lane/facing conditions
still hold and sparring is active. This is deliberately stricter than
treating an expired timer mid-tick as retroactive input eligibility.

The update adds three native C boundary regression tests (17 total
counter tests), without adding any new `DinoArena` fields, changing the
default 180-tick demonstration, switching controller mappings, adding
invulnerability, or introducing an arcade ROM dependency. Native NRO
compilation is not proof of on-device counter timing; the CI guest
replay and actual physical input still require separate verification.

## Stage 227 — original counter audio, opt-in preview

A successful Stage 225/226 counter event now triggers a freshly synthesized
820 Hz, six-tick, centered triangle cue (priority 4) inside the existing
integer-only 48-kHz, stereo C sound engine. A failed counter has no event
and no new cue. No extra voice slot, prerecorded asset, ROM data, or
platform-specific audio API was introduced. Priority remains below actual
damage and KO cues. The event travels through the same native arena → SFX
→ 800-PCM-frame-per-tick path used in Nintendo Switch and the desktop
bridge.

Existing eleven cue identities, their C PCM definitions and the default
eleven-cue WAV preview are left unchanged. The extra counter sound is
**optional** when generating a local demonstration:

```sh
python3 tools/dino_sfx_preview.py --include-counter --out /your/private/folder/counter-12-cues.wav
```

The default command, without `--include-counter`, still emits the original
eleven-cue, 30-tick-per-cue WAV sequence. The opt-in WAV appends the twelfth
counter cue after the unchanged original bytes. Both output modes refuse
to overwrite existing files. The automatic 180-tick original training
demo never emits DINO_EVT_COUNTER and must retain its earlier image and
PCM checksums; verification remains a separate CI gate.

Tests cover new cue identity and reproducible envelope expiry, legacy
WAV prefix identity, opt-in 12-cue WAV metadata, and real native gameplay
counter-event-to-PCM bridge behavior. These are host-native audio tests,
not proof of audible Switch console output or emulator counter controls.

## Stage 228 — reliable six-tick visual counter confirmation

The same on-screen `COUNTER!` message now persists for **six 60-Hz
simulation ticks** (100 ms) after a successful counter, rather than
only for the exact one-tick event flag. When a frame contains more
than one game tick, the visible caption survives the normal short
catch-up interval. This is **not** a promise of visibility during
arbitrarily long rendering stalls: after more than six simulated ticks
without a redraw, the feedback correctly expires.

The timer belongs solely to the Switch presentation loop and the
desktop host preview, **not to DinoArena**. A new portable C
`dino_arena_counter_feedback_tick(remaining, events)` helper consumes
the original one-shot `DINO_EVT_COUNTER`, returns six on success,
decrements once for each following simulated tick, and saturates at
zero. Replay gameplay state, ABI layout, collision, hit-stun, damage,
PCM and 180-tick demonstration inputs are unchanged. Reset, starting
the built-in demo, and switching to the viewer clear the caption.

The native desktop preview shows the same brief `COUNTER!` message
in its status line. Two new C-backed counter tests verify six-tick
duration, deterministic reset, non-counter event rejection, unchanged
arena state and desktop integration. Switch build and emulator guest
confirmation remain distinct checks; these host tests do not prove
physical controller latency.

## Stage 229 — executable guest counter + PCM witness, not HID proof

The `DINO_EMULATOR_SELFTEST` NRO now runs a second, independent,
**ROM-free, scripted** mini-scenario on ARM64, before its normal
180-tick arena replay. This uses a separate local `DinoArena` and
`DinoSfx`, leaving the interactive arena, audio device queue and
historical replay hashes unchanged.

It reports five rows in `sdmc:/cadillacs-counter-guest.csv`:

- `RESET`: empty local arena, no events.
- `ARMED`: actual 60-Hz C tick activates sparring, opening a 12-tick
  attack windup.
- `COUNTER`: next real C tick successfully interrupts the windup,
  preserves HP, applies 9 ticks of enemy stun and 48 ticks of cooldown;
  the same synthesized SFX produces nonzero 48-kHz PCM.
- `RECOVERY`: one later tick decreases enemy stun and cooldown, while
  the one-tick counter event clears.
- `WRONG_FACING`: a reset negative control faces away, cannot counter
  on the last windup tick and receives the ordinary telegraphed hit.

A strict Python verifier rejects absent, symlinked, oversized, malformed,
reordered, duplicated or altered CSV rows, including simulated evidence
that the counter dealt damage, generated no PCM, or blocked an invalid
back-facing hit. The NeXium runner collects the file from the actual
emulated SD only **after** the separately checked 180-tick guest trace,
and archives the independent pass/fail result. Six native tests compile
and run the *same* counter-probe C file on the host; these host-generated
fixtures themselves are **not** guest evidence.

The new witness never reads the original ROM, saves user inputs, or
changes the default gameplay/demo. It exercises actual Nintendo Switch
ARM64 game and synth code only once its NeXium CI completes
successfully. This scripted diagnostic does **not** claim that ZR was
delivered by HID, that an on-console button was pressed, or that a
physical speaker reproduced the cue. Those require separate evidence.

## Stage 230 — exact cross-architecture counter PCM fingerprint

The independent guest counter/PCM diagnostic from Stage 229 now records
the **full 64-bit FNV-1a checksum** of its first 800-frame, 48-kHz
interleaved stereo PCM block, rather than merely checking that at least
one PCM sample was nonzero. The shared portable
`dino_pcm_witness_feed()` function converts signed 16-bit samples
into explicit little-endian bytes before hashing, independent of host
or guest byte order. For the unchanged original 820-Hz counter cue,
the golden native C fingerprint is `1169E164EDF5FD7D`.

The verifier requires that exact uppercase 16-digit digest on the
`COUNTER` row, with pristine FNV seed `CBF29CE484222325` on rows
without generated PCM. A one-bit change in the reported digest, an
all-zeros/audio-silent substitute, or a lowercase/noncanonical
encoding fails the check. GCC tests compile the same arena, sound
engine, PCM hasher and guest probe that are linked into the NRO,
and include targeted tampering cases.

This is a **deterministic software PCM** comparison, not evidence that
audout submitted or played the signal. It does not claim genuine ZR
HID timing, hardware audio latency or source-game audio replication.
Regular training input, `DinoArena` ABI, the established 180-tick
replay and its historical PCM witness are unchanged. Stage 230
requires a new end-to-end GitHub Actions / NeXium run.

## Stage 231 — exact-impact counter eligibility at 60 Hz tick boundaries

The independently executed ARM64 guest diagnostic now appends five
negative-control rows to its Stage 229/230 five-row trace. It forces the
enemy windup to one remaining tick and attempts to counter in the same
tick as a forbidden player state is about to change:

- `LAST_HITSTUN`: final frame of player hit-stun.
- `LAST_ATTACK`: final frame of the existing attack animation.
- `LANDING`: a jump reaches ground level during that same update.
- `ATTACK_CHORD`: attack + counter are pressed simultaneously (with
  attack held on cooldown).
- `JUMP_CHORD`: jump + counter are pressed simultaneously.

In every case, **the defensive counter must be rejected**, the enemy's
telegraphed strike must still complete and deal its normal one HP of
damage, and the opponent enters the normal 48-tick strike cooldown.
The landing and jump-chord scenarios preserve their legitimate land
and jump-start event flags respectively, rather than masking them.

The 10-row guest CSV is checked in exact order against strict
expected event masks, health, cooldown, hit-stun, and PCM fields. The
same native C probe runs under GCC and as part of the real NeXium NRO;
new tests reject forged positive counter events, missing landing/jump
events and invalidly retained HP. This catches edge bugs where a
timer decrement or same-tick landing accidentally enables a ZR/H
counter too early.

These tests are scripted and run only against an originally invented
ROM-free training opponent. They are **not** native HID/ZR controller
delivery evidence, console latency measurements or Capcom gameplay.
They do not alter the live counter rules, ABI layout or historical
180-tick replay/audio checksums.

## Stage 232 — compiler/optimizer and UBSan portability gate

The Stage 229–231 ROM-free guest-counter probe is now compiled and
executed on the native host with multiple **independent compiler
configurations**: GCC `-O0`, GCC `-O2` (reference), GCC `-O3`,
and Clang `-O2`. The compiled programs must serialize exactly the
same 10-row guest diagnostic bytes, including the `1169E164EDF5FD7D`
first-block counter PCM checksum and the five rejected last-impact
counter cases. A further `-fsanitize=undefined` host executable must
exit cleanly with the identical trace.

The native CI workflow explicitly requires Clang to be installed so
compiler diversity cannot silently disappear in GitHub Actions. This
step exercises the *same* C arena, integer PCM synth, FNV64 hasher and
counter guest-probe used in the self-test NRO. It catches compiler
sensitivity and undefined behavior early without importing any original
arcade asset. It is **host compiler parity**, not proof of successful
Switch console input or physical audio output.

All changes are test/workflow-only: the interactive arena, counter rules,
guest witness schema, ABI, and historical 180-tick replay/PCM fingerprints
remain unchanged. The NeXium guest job must separately confirm that the
ARM64 build reproduces the golden 10-row report.

## Stage 233 — second-counter round-trip after the complete 48-tick recovery

The scripted, ROM-free guest counter diagnostic now continues after its
first successful interrupt and recovery frame to establish a full
**time-bounded combat loop**. An `EARLY_REPEAT` input at tick 4 must
produce no counter while the opponent is stunned (7 ticks) and cooling
down (46 ticks). After exactly 46 additional idle updates (48 elapsed
game ticks since the first successful counter), `REARMED` must be
recorded at tick 50 with no damage to either character, zero cooldown,
zero stun and a new 12-tick enemy attack telegraph. A fresh counter
edge on tick 51 must interrupt that telegraph and reset the opponent's
stun/cooldown to exactly 9/48 ticks.

The newly allowed `SECOND_COUNTER` is independently synthesized
again as an isolated ROM-free cue and its 800-frame 48-kHz PCM must
produce the same nonzero audio and canonical FNV64 digest
`1169E164EDF5FD7D` as the first legal counter. The diagnostic has
grown from 10 to **13 guest state rows** (plus a CSV header); the five
Stage 231 last-impact negative cases remain unchanged. The strict
verifier refuses early repeats, wrong cooldown expiry, missing new
windup, or altered second-counter PCM. Two new native tests cover the
normal roundtrip and tamper cases.

The 180-tick historical replay and interactive gameplay use entirely
separate state; this is a scripted NRO selftest, not a real NeXium
HID/ZR button-press attestation or physical speaker measurement.

## Stage 234 — optional real NeXium keyboard T → guest libnx ZR witness

NeXium's public default keyboard binding maps `T` to Switch `ZR`
(`nexium-gui/src/controller_config.rs`). The existing NeXium guest
workflow now *optionally* attempts this external X11 key **only after**
the original, separate 900-tick guest audio-stress CSV has recorded
`STRESS_DONE`. If the guest is late or the emulator doesn't accept the
key, the new diagnostic honestly reports `INCONCLUSIVE` without
invalidating the independent 180-tick gameplay replay.

The CI-only NRO records a valid `padGetButtonsDown(HidNpadButton_ZR)`
edge, latches it across a possible render frame containing **zero**
simulation ticks, and waits for the real
`step_pressed & DINO_ARENA_COUNTER` in a normal 60-Hz update. Only
then it creates an independent, tightly controlled original-training
counter-ready `DinoArena`, executes the **actual consumed input**,
and writes two bounded rows (`READY`, `HID_COUNTER`) to the
emulated SD filesystem. A separate strict verifier validates its
event bit, one-shot edge, no damage, 9-tick enemy stun and 48-tick
cooldown. Host-key injection alone never qualifies as a pass.

The `guest-counter-hid-evidence.json` may become
`GUEST_LIBNX_ZR_EDGE_AND_COUNTER_EFFECT_WITNESSED` only when those
guest-written rows have been collected from an actual NeXium NRO;
otherwise it says `INCONCLUSIVE_NO_VALID_GUEST_ZR_COUNTER_EVIDENCE`.
This is a **prepared training arena** and establishes neither natural
combat timing under physical play, Joy-Con hardware latency nor
speaker output. The scripted Stage 229–233 guest counter scenarios
remain separately validated and are never substituted for the HID
witness.

The new validation executes only in `DINO_EMULATOR_SELFTEST` builds.
Normal NRO behavior, original training graphics and art, classic
replay hashes, and the 900-tick audio-stress collection are unchanged.
Two independent new test paths check strict guest CSV acceptance and
delayed X11 T-key dispatch, including rejection of fake/missing events.

## Stage 235 — exact PCM proof bound to a guest-origin ZR counter

The optional genuine NeXium keyboard T → libnx ZR test from Stage 234
now also tests the counter's **actual synthesized first PCM block**,
rather than relying on the counter event bit alone. Only when the NRO
has witnessed `padGetButtonsDown(ZR)`, carried that edge into a
normal 60-Hz `step_pressed & DINO_ARENA_COUNTER`, and executed a
counter in a controlled independent training arena does it reset
`DinoSfx`, consume the resulting C event, render 800 stereo frames,
and hash every 16-bit sample with the portable
`dino_pcm_witness_feed()`.

The strict optional guest report contains two rows:
`READY` must contain the untouched PCM FNV64 seed
`CBF29CE484222325` and `pcm_nonzero=0`; `HID_COUNTER` must
contain an actual generated nonzero cue and the exact golden PCM
digest `1169E164EDF5FD7D` from the original ROM-free counter synth.
The C code writes computed, rather than prescribed, state and PCM
values. The verifier rejects silent output, incorrect samples,
noncanonical/lowercase checksums, incorrect gameplay events and
missing/reordered rows. Local tests validate the grammar and host
conditions only — they are never considered actual NeXium evidence.

This **software synthesized PCM** proof does not establish speaker
playback, real Switch Joy-Con hardware, physical input latency,
or a naturally encountered counter opportunity. The complete
180-tick replay and the existing 900-tick guest audout health
window are unchanged; the extra synth buffer is local to the
optional post-stress guest diagnostic and never submitted to audout.

## Stage 236 — fix verified guest ZR PCM verifier failure

Stage 235 Python CI (commit `91fcccb0`) exposed one false-negative
test: the new guest `READY` record has **11 columns** after the
addition of `pcm_nonzero` and `pcm_fnv64`, but its expected-list
entry had only 10 values. This rejected an otherwise valid fixture;
it was not evidence of a live Switch gameplay failure.

The verifier now requires `hid_edge=0`, `pcm_nonzero=0`, and
`pcm_fnv64=CBF29CE484222325` in the `READY` row, alongside the
unchanged 11-field `HID_COUNTER` expectation. Two additional
regressions check column counts and reject missing/corrupt ready
audio fields. A separate literal schema/fixture comparison passed;
GitHub Actions and real NeXium guest results remain independent
and must be confirmed on the new commit.

Only diagnostic validation and tests are affected. Core gameplay,
Switch ROM-free audio synth, 180-tick replay and original game data
are unchanged.

## Stage 237 — fail-closed preflight before optional NeXium ZR injection

The **external** host T/ZR injector previously treated any text line
beginning `STRESS_DONE,900,` in a bounded guest file as sufficient
evidence to send the key. This could include a malformed, duplicated,
truncated or otherwise partial guest audio-stress report.

It now accepts the file **only after** it contains all seven ordered
`START` / five `CHECKPOINT` / `STRESS_DONE` rows, the exact
full current CSV column schema, canonical unsigned counters and
16-character uppercase PCM checksums, the exact 0/150/.../900
simulated-tick checkpoints, aligned arena/audio/PCM clocks,
and active/valid two-page audio queue accounting. A symlink, missing
file, duplicate row, incomplete report, false terminal marker, or
bad checkpoint keeps the host X11 key **unsent**.

This light, file-completion **preflight is not a substitute** for the
separately executed full guest audout stress and real HID timeline
verifiers. Its only job is to avoid disrupting unfinished audio
measurements or claiming that a host key was delivered prematurely.
Additional tests construct a complete synthetic seven-row fixture
and verify that truncated, forged, noncanonical and clock-corrupted
versions never arm the injection. Synthetic fixtures are never
interpreted as NeXium execution evidence.

No original ROM, main gameplay timing, counter rules, source audio,
Switch framebuffer or guest PCM synthesis has changed; only the
optional CI-side host input gate and its tests have been strengthened.

## Stage 240 → Stage 241 — real NeXium ZR/PCM regression gate

The six PR workflows on Stage 237 commit `1e8633ab` all passed:
`Nintendo Switch native bootstrap`, `Native ROM-free gameplay visual
smoke`, `CPS-1 Python tools` (1,413 tests, one expected skip), the
ROM-free privacy gate, the opt-in PCM ramp guest proof, and the full
baseline / extra-poll NeXium workflow including its paired audio audit.
Both actual guest modes produced `GUEST_LIBNX_ZR_EDGE_AND_COUNTER_EFFECT_WITNESSED`
and a counter software-PCM FNV64 `1169E164EDF5FD7D`.
The paired audout accounting found 119 skipped baseline versus 116
skipped experimental blocks across two **not causally matched** runs;
it does not establish that the experimental mode improves audio.

Stage 241 promotes the real HID counter proof from an **optional,
locally verified guest-side artifact** into a **separate required paired
PR gate**. The new script
`tools/verify_nexium_guest_counter_hid_paired.py` reads the recorded
two-row guest CSV and the saved guest-verifier JSON **for each mode**
and independently re-runs `verify_nexium_guest_counter_hid.verify`.
Any absent guest CSV, incorrect ZR event, altered exact synthesized PCM,
duplicated JSON property, mismatched recorded verdict, symlink, truncated
report, or fabricated mode label makes this new paired step fail.

For both modes, it *also* revalidates the actual 900-tick audout report,
mode-binding JSON, and compiled NRO SHA-256 with the existing
`verify_nexium_audio_paired_artifacts.validate_binding`; baseline
and experimental NRO hashes must differ. Its own bounded JSON
`paired-real-zr-counter-pcm-attestation.json` is emitted only on
success and included in the completed paired NeXium CI artifacts.
Six additional synthetic unit tests exercise valid-shape parsing and
deliberately missing, modified, duplicate, swapped or unbound inputs;
synthetic fixtures are **not** guest execution evidence.

The guarantee is deliberately limited: two valid ROM-free diagnostic
witnesses from CI guest runs, consistent with independently checked
audio-mode/NRO bindings. It is **not** cryptographic proof of in-guest
file creation, natural encounter timing, Joy-Con input latency, audible
speaker output, or a causal benefit of extra polling. Production
controls, gameplay, PCM synthesis, actual ROM contents and cover art
have not changed. The new required CI step must be executed and
confirmed on its own fresh commit before Stage 241 is considered done.

### Stage 241 audit correction — real artifact mode-binding paths

Before the Stage 241 paired gate ran, inspection of the *actual*
Stage 240 baseline and extra-poll artifacts exposed a verified
provenance bug in its new CI arguments. The new CLI initially passed
`guest-audio-stress.csv` to
`verify_nexium_audio_paired_artifacts.validate_binding()`, but the
guest mode-binding SHA-256 was generated for the **already validated
`guest-audio-stress-evidence.json`**, not the raw CSV. These two
different files are not interchangeable.

Both actual Stage 240 artifact ZIPs were independently inspected:
each recorded audio binding SHA-256 matches its own
`guest-audio-stress-evidence.json` bytes and the matching real NRO
SHA-256; it intentionally does not match the raw stress CSV SHA-256.
Both raw guest counter-HID CSVs have the exact 11-field READY and
HID_COUNTER rows and exact counter software-PCM
`1169E164EDF5FD7D` expected by the new strict verifier.

The CI arguments now pass the validated JSON for **both modes**.
A new negative contract test requires those two exact JSON paths,
and rejects reverting to the raw CSV paths. This is an input-path
correction for the new Stage 241 audit, not an alteration of the
recorded guest data, ROM-free gameplay, audio renderer or original
Capcom ROM.

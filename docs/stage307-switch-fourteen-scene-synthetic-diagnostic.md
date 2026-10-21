# Stage307 — Switch-ready 14-scene CPS-1 compositor diagnostic timeline

## Purpose

Stage305's C-versus-Python differential contract tests fourteen invented
CPS-1 VRAM / OBJ / scroll / priority / palette states. Stage306 checks
the user's original CPS-1 graphics ROM at **all 172,032 tile decode
positions**, finding zero C/Python mismatches across **25,165,824
four-bit pen indices**. These are complementary *static graphics*
and *synthetic scene* checks. Neither reproduces original gameplay.

The Nintendo Switch diagnostic application's existing
`source/main.c` loader accepts `sequence.bin`
in the versioned `CPS1SEQ1` format and displays its
frames with the portable native C compositor.

Stage307 adds a deterministic **ROM-free** producer for a fourteen-frame
diagnostic sequence, in exactly Stage305's scenario order, so the
Switch viewer can exercise all scenarios with the user's **separately,
privately installed and owned** `gfx.bin`.

## Create a local diagnostic sequence

From a checkout of the project:

~~~sh
python tools/cps1_synthetic_scene_sequence_307.py \
  --out /private/switch-test/sequence.bin \
  --report /private/audits/stage307.json \
  --fps 2
~~~

Copy `sequence.bin` to the Switch application's existing
SD location:

    sdmc:/switch/cadillacs-dinosaurs-switch/sequence.bin

The NRO still requires the user-owned full 4-MiB CPS-1 graphics
region `gfx.bin`, assembled privately from their authorized ROM:

    sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin

**Neither the original `dino.zip` nor derived `gfx.bin`
should be committed, uploaded to public CI, or redistributed.**

The scene sequence has no ROM bytes or game images: it encodes only
*invented* tilemap words, RGB palettes, scroll values, sprite objects,
priority flags and video-control values. It is not an arcade recording.

## Exact frame order

The 14 frames (zero-based) correspond to:

| Frame | Synthetic compositor test |
|---:|---|
| 0 | priority_sprite |
| 1 | unmasked_sprite |
| 2 | priority_transparent_bit |
| 3 | priority_group_selective |
| 4 | transparent_palette_unused |
| 5 | palette_channels_shift |
| 6 | scroll1_priority |
| 7 | scroll1_unmasked |
| 8 | priority_group0_unmasked |
| 9 | priority_group1_unmasked |
| 10 | priority_group2_unmasked |
| 11 | priority_group3_unmasked |
| 12 | rowscroll_flip |
| 13 | sprite_under_layers |

At the default **2 FPS**, each frame holds for half a second.
The existing NRO can pause and step through sequence frames;
these controls are part of the already-existing diagnostic viewer.

## Integrity and privacy gate

The generator requires:

- Exactly 14 distinct scene states in the established order, without
  changing source CPS-1 tile or animation assets.
- One fully formed 62,510-byte `CPS1SCN1` snapshot per case, with
  its own length, CRC32 and canonical layer-enable flags.
- The strict `CPS1SEQ1` binary format with 20-byte
  header, exactly 14 frames and frame rate 1..60.
- Whole-payload CRC32 and 14 verified inner scene CRC32 values.
- All 14 serialized scene blobs distinct by CRC32; repeat or missing
  scenarios cannot accidentally be described as full coverage.
- Output written once, exclusively, with restrictive permissions,
  to a private location outside the repository, with no overwrite.
- Optional private aggregate-only receipt containing scenario names,
  frame counts, schema version and **false flags** for original MAME,
  actual gameplay, captured palette/VRAM/OBJ, INP/WLF replay and
  physical Switch confirmation.

Success status:

`SYNTHETIC_CPS1_SWITCH_SCENE_SEQUENCE_READY_NOT_GAMEPLAY`.

## Public tests

~~~sh
python -m unittest discover -s tests \
  -p 'test_cps1_synthetic_scene_sequence_307.py' -v
~~~

Sixteen ROM-free tests cover deterministic sequence generation,
headers, each frame CRC, outer CRC, distinct cases, supported frame
rates, tampered headers, repeated frames, missing/incomplete snapshots,
symlink-safe exclusive output and appropriately limited provenance.

## Important limitations

The producer, even if all tests pass, only establishes a
**Switch-compatible diagnostic scene file**, not on-console
execution. The framebuffer has **not** been inspected on physical
Nintendo Switch hardware, and no real CPS-1 game video frame,
original palette RAM, buffered sprites, vblank timing or control
recording is claimed.

The central game-verification blocker remains a compatible private
historical Windows/Wine MAME 0.106 execution environment for the user's
authorized ROM and original `dino.inp` / `dino.wlf`
recordings.

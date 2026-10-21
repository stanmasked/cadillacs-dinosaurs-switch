# Stage308 — fully ROM-free graphics for the existing Nintendo Switch CPS-1 diagnostic viewer

## Why this exists

Stage307 created a deterministic, fourteen-frame CPS1SEQ1 sequence of invented
RAM/OBJ/priority/palette states, but the native NRO still required a locally
assembled **original** gfx.bin. Stage308 removes this dependency for technical
**diagnostic viewing only**: it generates a compatible, unmistakably artificial
4,194,304-byte graphics input in the layout the already-existing C decoder
expects.

No original dino ROM, ROM graphics, copyrighted game sprite or gameplay data
is used. There is no ROM download, ROM extraction or emulator capture.

## Generate the two local files

Run from a checkout containing Stages307 and 308. Pick **unused paths in an
existing directory outside the repository**. The commands deliberately refuse
overwrites and set restrictive permissions.

~~~sh
mkdir -p /private/switch-diagnostic
python tools/cps1_synthetic_gfx_fixture_308.py \
  --out /private/switch-diagnostic/gfx.bin \
  --report /private/switch-diagnostic/stage308.json

python tools/cps1_synthetic_scene_sequence_307.py \
  --out /private/switch-diagnostic/sequence.bin \
  --report /private/switch-diagnostic/stage307.json \
  --fps 2
~~~

The first file is synthetic 4-MiB CPS-1 planar data, not an arcade ROM.
It has a 32-KiB deterministic artificial pattern repeated 128 times;
a visible byte marker makes that provenance explicit. The second is the
Stage307 fourteen-frame synthetic scene sequence (875,160 bytes).

For a local diagnostics run, copy only these two newly produced files to:

~~~text
sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin
sdmc:/switch/cadillacs-dinosaurs-switch/sequence.bin
~~~

Use the existing NRO's sequence playback controls to pause/step scenes.
A valid input pair and a successful NRO compilation **do not by themselves
prove** that the Switch framebuffer was displayed correctly.

If a private original gfx.bin already exists at that path, **do not overwrite
it without explicitly backing it up**. A separate SD card/test environment is
preferable. Never commit either generated .bin file to GitHub, even though
this Stage308 variant is synthetic; the public binary privacy gate stays
strict and should never be weakened.

## Test

~~~sh
python -m unittest discover -s tests -p 'test_cps1_synthetic_gfx_fixture_308.py' -v
~~~

The ROM-free tests cover byte-exact size, deterministic regeneration,
all 16 four-bit pen values, safe exclusive private output, refusal to follow
symlinked paths, provenance limits, and compatibility with Stage307.

When GCC is present, an integration test compiles **the actual portable C
tile and scene compositor used by the NRO** and renders all fourteen invented
scenes using the artificial gfx region. It verifies relevant intended
metamorphic effects and compares two selected full RGBA frames against the
independent Python compositor. This verifies host-native pixel behavior,
**not Switch GPU, display latency, emulator execution or original game
frame parity**.

## Evidence boundary

- Synthetic data generation and host C/Python agreement can be checked in
  public CI, with zero original ROM assets.
- Only an actual device/emulator execution of the NRO with the synthetic
  files can establish the application's real display behavior.
- Reproducing original Cadillacs and Dinosaurs still separately requires a
  privately validated original game ROM, compatible historical MAME 0.106
  runtime, controlled input replay and actual game-state capture.
- Keep this Draft PR stacked on Stage307, and do **not** merge into main
  based solely on synthetic diagnostic CI.

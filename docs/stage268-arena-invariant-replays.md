# Stage 268 — native ROM-free arena invariants

This stage turns attention from the NeXium X11 measurement chain back to
the **actual portable C training arena**, which remains a standalone
ROM-free diagnostic prototype, NOT reconstructed CPS-1 arcade gameplay.

New `tests/test_dino_arena_invariant_replays.py` builds the real
`source/dino_arena.c` with GCC `-O0` and GCC `-O2` (and Clang
`-O2` if available) using strict warnings. It executes:

- 24 deterministic 900-tick randomized-input playthroughs against
  world bounds, HP limits, jump, combo, visual effect and event rules;
- 12 identical 600-tick runs across compilers/optimizations with an
  independent full-field state comparison on **every** step;
- 1,200 tick-by-tick comparisons of ordinary inputs against identical
  inputs with unknown upper bits (these bits must be ignored);
- a 1,500-tick warm-up, full reset, then 600-tick replay comparison
  against a fresh arena;
- all 256 held-direction/pressed-button mask combinations with
  hostile simultaneous input bits;
- null-pointer API safety for each compiled C implementation.

An additional adversarial rule checks counter-only effects, one-tick
DODGE and KO events, and that the invented dummy cannot exceed arena
bounds. PR CI compiles the real native C implementation, not a copied
Python physics model.

No ROM, console firmware, private artwork, game engine gameplay
modification, native Switch UI change, or physical controller timing
claim is involved. Cross-compiler equivalence is not an emulator
guest-frame proof; the separate NeXium CI remains authoritative for
guest execution. This stage does NOT claim the original Cadillacs and
Dinosaurs fighting mechanics are implemented.

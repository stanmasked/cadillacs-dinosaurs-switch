# Stage 269 — real native C game-state scenario observation

New ROM-free headless tool `tools/dino_arena_scenario_trace.c`
compiles with the **actual existing** portable C training arena
(`source/dino_arena.c`), not reimplemented Python physics. It prints
explicit, bounded CSV rows on each 60 Hz simulation tick, including
player/target state, combat events and counter-caption TTL. No private
arcade data or Nintendo runtime is required.

Four reproducible scenarios are included:

1. **Target practice, 120 ticks:** seventy steps of movement, exactly
   three timed attacks at steps 75, 90, 105, one finisher and target KO.
2. **Natural enemy pursuit, 140 ticks:** spar toggled at step zero,
   enemy advances naturally for 116 ticks, a one-tick defensive
   counter interrupts windup at step 116, then the feedback decays.
3. **Jump dodge, 22 ticks:** an explicitly staged starting x-position,
   spar begins its windup, a jump results in a single DODGE instead
   of player damage.
4. **Player KO, 5 ticks:** a documented staged one-hit-KO setup
   proves the KO event occurs exactly once, with no repeated injury
   event on subsequent ticks.

The tool fails nonzero if any expected gameplay route fails. The new
`tests/test_dino_arena_scenario_trace.py` compiles and runs it under
GCC -O0, GCC -O2 and, when installed, Clang -O2. It demands the
**same complete CSV bytes** across all compilers, 287 data records,
one row per simulated tick, and verifies the expected game events and
arena bounds from the genuine C output.

This is a debugging/replay trace of an *invented training prototype*.
It does NOT prove reconstructed Cadillacs and Dinosaurs CPS-1
mechanics or original sprites. It is not a NeXium guest input
measurement or end-to-end display latency test. No original ROM,
console firmware, private artwork, game production source or main
branch is modified.

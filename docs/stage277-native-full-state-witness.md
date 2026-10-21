# Stage 277 — canonical full training-arena state witness

The Stage274 native C input adapter originally accumulated one 64-bit FNV-1a-style digest per tick over only six state values: simulation tick, player X/Y/Z, cumulative successful hits and the current tick's event bitmask. It was therefore possible for **player HP, target HP, stun, invulnerability, combo timing, attack cooldown and other fields to diverge without changing the reported state digest**.

Stage277 adds a **second**, version-independent field-by-field witness, while preserving the historic `state_digest_fnv64` key for comparisons with previous private receipts.

## Full-state diagnostic

For each executed native C tick, the adapter hashes **all 30 declared DinoArena scalar members** in a fixed documented order, each coerced to `uint32_t` and fed into the existing four-byte, low-byte-first FNV mixing routine:

1. Player position and motion: `x,y,z,vz`.
2. Target position: `dummy_x,dummy_y`.
3. Tick and hit totals: `ticks,successful_hits`.
4. Facing, health, stun, cooldown, player/target animation state, combo state, impact TTLs.
5. The per-tick `events` bitmask.

The output adds:
- `full_state_digest_fnv64`: 16 lowercase hexadecimal characters per native run.
- `full_state_fields`: exactly 30.
- `round_full_state_digest_sha256`: SHA-256 over the **ordered list of per-round full-state digests**, emitted by the private Stage275/276 segmented driver.
- `full_state_fields_witnessed`: expected count of 30.

The aggregate driver fails closed on missing or malformed full-state receipts. GCC/Clang comparisons now include full-state digests, not merely the legacy six-field state digest.

**Important:** This is a deterministic *diagnostic checksum*, not cryptographic proof or native Switch/video parity. FNV hashes can collide. The input data is still a nominal P1 stress workload for an invented ROM-free training arena, **not an authenticated WolfMAME 0.106 replay of Cadillacs and Dinosaurs**.

## Regression demonstrating the previous blind spot

A synthetic test compiles the unchanged C training arena alongside a temporary deliberate mutant whose **initial player HP is 4 instead of 5**, leaving all other C code intact. With the same synthetic nominal P1 inputs:

- The historic `state_digest_fnv64` is **identical**.
- The new `full_state_digest_fnv64` is **different**.
- The original, nonmutated Git code is not modified by this experiment.

An additional test enumerates all actual fields declared in `source/dino_arena.h` and compares them to the 30 canonical fields in the C witness. CI fails if a future developer adds a combat-state member but forgets to update the full-state digest.

## Run completely ROM-free tests

```sh
python3 -m unittest discover -s tests -p 'test_dino_arena_full_state_witness.py' -v
```

The six new tests include field coverage, old/new digest compatibility, HP mutation detection, GCC versus Clang parity, private segmented driver aggregation and repeated deterministic runs. No original Capcom ROM, original INP/WLF, screenshots or derived full P1 byte stream is tracked in GitHub. Original user assets stay private.

This Draft stage is stacked on PR #84. It changes only the native witness and its verification, **not the arena's physics, collision, AI, rendering, audio or approved artwork**.

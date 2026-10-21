# Stage 275 — private recorded-input training rounds

The original WolfMAME 0.106 `dino.inp` input sequence is valuable as a stress workload for the independent ROM-free training arena; however, a single continuous invented sparring match can end early in player defeat. Stage274 proved this on a 314,951-tick private input workload: only one swing fired before the player was defeated. The remaining ticks no longer meaningfully exercised combat.

Stage275 uses independent **1,200-input-frame rounds** (about 20 seconds at the assumed, unverified 60 frames/s). Each round resets the invented C99 arena and starts a fresh optional sparring session. It cannot inherit a previous round's player death or cooldown, so the input workload reaches far more training combat paths. The exact recorded stream is never published.

## Private usage

```sh
python3 tools/wolfmame0106_private_round_stress.py \
  --inp /private/wolfmame/dino.inp \
  --wlf /private/wolfmame/dino.wlf \
  --round-frames 1200 \
  --compiler gcc --compiler clang \
  --out /private/audit/dino-independent-training-rounds.json
```

The tool:
- Validates the WLF/INP pairing using the same strict 32-byte header and 124-byte frame size as Stage270, then extracts **only nominal P1** active-low byte position 19 into memory.
- Compiles the **existing actual** `source/dino_arena.c` and Stage274 C adapter independently using the requested host compiler(s).
- Runs all input slices with fresh arena state, in both the ordinary static-target mode and the **invented** sparring mode.
- Requires exact aggregate and SHA256(digest list) equality across compilers. Fails closed if a mode produces inconsistent frame counts, fails to compile, raises native errors, or has differing digest results.
- Writes only aggregate counts and a digest of each mode's digest sequence. The private input, original P1 byte stream, per-frame input deltas, ROM, MAME assets, or screenshots **do not appear** in the Git repository or report.
- Refuses to write output inside the public repository; refuses symlinked private recording paths and overwriting existing audit output.

## Verified example on private user-held data (not in GitHub)

The original INP/WLF pair has 314,951 input records. The *same exact Git* C core and adapter SHA-1 Git blobs used by PR #82 were checked in a local investigation before this change. A read-only 1,200-record segmented audit split them into **263 independent rounds**, final length 551, for both modes and both GCC-O2 and Clang with UBSan: **1,052 native executions**. The results matched across the two compilers; total invented sparring swings **2,601**, training jumps **825**, successful training hits **424** across 263 rounds. This is a **workload-coverage** result, not comparison to the arcade game.

The user-owned original INP/WLF are not included as test fixtures. CI uses only the six new synthetic tests in `tests/test_wolfmame0106_private_round_stress.py`, including full/short slices, deterministic repeated compilation, invalid requests, optional Clang parity, a 240-frame fake WolfMAME pair, and direct CLI invocation.

## Limitations

- The INP interpretation remains a structural hypothesis pending matching WolfMAME 0.106 playback.
- Resetting every 1,200 records and synthetic sparring are testing inventions, **not** original Capcom game mechanics.
- Artificial round boundaries can generate new press edges for a button held over a boundary. Totals in this report are **not** counts of authentic consecutive arcade actions.
- This does not verify original animation, enemy AI, gameplay speed, video frame timing, physical Switch hardware or input-to-display latency.

PR #83 is stacked on Draft PR #82. Preserve privacy and re-run CI after any new commit.

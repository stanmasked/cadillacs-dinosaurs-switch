# Stage 278 — localizable full-state checkpoints in ROM-free native training replay

The Stage277 `full_state_digest_fnv64` covers all 30 `DinoArena` scalar fields at every simulated tick, but the final cumulative digest alone cannot tell *when* a mismatch arose during a multi-hundred-thousand-record input stress test. Stage278 adds **opt-in periodic checkpoints** and an independent log comparator. No game physics, graphics, audio or event timing changes.

## Native execution

```sh
# A private workstation only: give this native executable a private P1-byte
# projection via stdin; do not commit that stream or these checkpoint logs.
./arena_stress --checkpoint-every=1200 < /private/dino_p1_projection.bin \
  1>/private/checks/gcc-receipt.json 2>/private/checks/gcc-checkpoints.log

# Same protected P1 sequence with the independently compiled Clang binary.
./arena_stress_clang --checkpoint-every=1200 < /private/dino_p1_projection.bin \
  1>/private/checks/clang-receipt.json 2>/private/checks/clang-checkpoints.log

python3 tools/dino_native_compare_private_checkpoints.py \
  --reference /private/checks/gcc-checkpoints.log \
  --candidate /private/checks/clang-checkpoints.log \
  --input-frames 314951 --checkpoint-every 1200 \
  --out /private/checks/comparison.json
```

**Note:** The example projections are private temporary products of the user's INP, not included in the repo. Generating the local stream is permitted only for authorized input records. To avoid storing any private stream on disk, pipe the parsed P1 bytes directly to the C executable. The existing Stage274 private driver already performs extraction in memory.

`--checkpoint-every=N` accepts only positive ASCII decimal integers from 1 to 10,000,000, once per process. If not specified, behavior and the existing one-line stdout JSON remain unchanged. If specified, the C tool emits lines of the form `DINO278_CHECKPOINT frame=1200 full_state=…` to **stderr**, one at each N-input-frame boundary and one at the final partial interval (never repeated when already aligned). Its last checkpoint equals the final 30-field cumulative hash in the ordinary stdout JSON.

The comparator requires the exact expected series of checkpoint frame numbers, correct lowercase 16-digit digests, bounded ASCII logs, strictly ordinary non-symlink files, and refuses to put derived receipts in the public repository. For a divergence it reports the **first observed mismatching checkpoint** and the **last agreeing checkpoint**, giving a bracket in which the mismatch arose. It cannot know the precise failing simulation tick without a denser repeat, and it cannot tell which implementation is correct. No individual checkpoint log or original button stream is written into its JSON summary.

## Local evidence on the private 314,951-record input workload

GCC `-O2` and Clang `-O2` were tested with the **actual unchanged C arena** and this exact Stage278 adapter:

| Interval | Checkpoints, per mode | GCC/Clang |
|---|---:|---|
| Every 60 records | 5,250 | Equal |
| Every 600 records | 525 | Equal |
| Every 1,200 records | 263 | Equal |

Both default and deliberately invented sparring modes matched at every checkpoint, across **12 complete native executions**. The original `dino.inp`/`dino.wlf`, Capcom ROM, derived P1 byte sequence and raw checkpoint logs remain private and are not committed. This is not WolfMAME emulation or original game parity.

## ROM-free CI

```sh
python3 -m unittest discover -s tests -p 'test_dino_native_full_state_checkpoints.py' -v
python3 -m unittest discover -s tests -p 'test_dino_private_checkpoint_comparator.py' -v
```

Sixteen synthetic tests cover unchanged default stdout receipt, exact checkpoint spacing including partial last interval, rejection of malformed/repeated command flags, cross-compiler checkpoint parity, artificial HP mutation detection at the first checkpoint, strict input-log grammar and temporal ordering, symlink refusal, and the first-difference bracket. GitHub tests do not use the original user recording or ROM.

This stage is stacked on Draft PR #85, pending its own CI. It advances reproducible **native training-state debugging**, not authentic CPS-1 audio, sprites, stages, physical Switch verification, or INP-to-video synchronization.

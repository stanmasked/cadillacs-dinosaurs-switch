# Stage 274 — private WolfMAME input as a native training-arena stress load

This stage is the first concrete bridge from a **locally held WolfMAME 0.106 P1 input recording** into the *independent, ROM-free C training arena*. It exercises the actual native C99 movement, jump and attack code for long, irregular sequences. **It is NOT playback of the original Cadillacs and Dinosaurs game.**

## Native adapter

The executable `tools/dino_arena_recorded_input_stress.c` accepts **exactly one active-low nominal P1 input byte per simulation tick from stdin**. The six ordinary CPS-1 input positions map to our *invented* DINO_ARENA button vocabulary:

| P1 bit | Static INP meaning | Training-arena input |
|---|---|---|
| 0 | right | DINO_ARENA_RIGHT |
| 1 | left | DINO_ARENA_LEFT |
| 2 | down | DINO_ARENA_DOWN |
| 3 | up | DINO_ARENA_UP |
| 4 | button 1 | DINO_ARENA_ATTACK |
| 5 | button 2 | DINO_ARENA_JUMP |

Both opposite directions are passed unchanged; they are **not** silently changed into a real arcade directional decision. Button 1/2 events are rising-edge inputs: a long-held button does not trigger an attack/jump on every tick. Coin/Start, P2 and P3 are intentionally **excluded**. The invented sparring enemy can be explicitly enabled with `--spar`, but original INP bytes are *never* interpreted as training-only sparring/counter commands.

Outputs are strictly **aggregate** counters, bound checks and a deterministic 64-bit state digest. No input sequence, user ROM, original game art, original PCM or screenshots are embedded in the executable or emitted as a stream.

## Private end-to-end run

On a workstation that has the user-owned private recording, GCC, and this repository:

```sh
python3 tools/wolfmame0106_private_arena_stress.py \
  --inp /private/wolfmame/dino.inp \
  --wlf /private/wolfmame/dino.wlf \
  --out /private/audits/dino-native-arena-input-stress.json
```

The Python driver:
1. Enforces the Stage270 `dino` 0.106 INP/WLF pair binding and exact `32 + 124 × frames` file length used by our parser.
2. Extracts **only P1 active-low byte at input-record position 19** into memory, does not create a derived full input file.
3. Compiles `source/dino_arena.c` with the C adapter in a temporary private directory.
4. Performs one ordinary and one **explicitly synthetic sparring** run; both process the same nominal sequence and must match the WLF frame count.
5. Saves a private aggregate report that expressly states original emulator playback and original-game visual/physics parity are **not verified**.
6. Refuses a report destination within the public repository, and refuses symlinked private inputs.

The full native training sequence is a **stress workload**, not a source of animations or proof that our input timing equals CPS-1. A simulated tick consumes one recorded port byte; actual WolfMAME reproduction, game frames, original enemy logic and original ROM data are still required to establish accuracy.

## Public, ROM-free CI

```sh
python3 -m unittest discover -s tests -p 'test_dino_arena_recorded_input_stress.py' -v
```

Seven synthetic checks exercise repeated/held inputs, attack and jump edges, long deterministic workloads, a deliberately invented sparring mode, invalid invocation and GCC optimization parity. An additional Clang-versus-GCC test runs when Clang is installed. **There is no original .inp/.wlf fixture in GitHub.**

This is stacked on Draft PR #81 (Stage273); it must pass its own CI before integrating with upstream Draft branches. The full legacy WolfMAME 0.106 emulator and original game are still not running in our current environment.

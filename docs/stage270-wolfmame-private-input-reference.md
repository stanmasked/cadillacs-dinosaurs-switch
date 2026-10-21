# Stage 270 — private WolfMAME 0.106 INP reference research

This stage adds **ROM-free tooling only** for inspecting a user-owned `dino.inp` recording together with its `dino.wlf` metadata. Neither file, nor any personal ROM, captured artwork, screenshot, PCM or per-frame original-input sequence is included in the repository.

## Why this changes the previous input interpretation

The CPS-1 driver declares input port `IN1` as a 16-bit active-low value. Bit masks `0x0001..0x0020` control player 1; `0x0100..0x2000` control player 2. In the observed historical INP record (32-byte header and 124-byte record stride), the 16-bit IN1 pair occupies record offsets **18 and 19**:

- offset **19** — low 8-bit portion, nominal P1.
- offset **18** — high 8-bit portion, nominal P2.
- offset **23** — separate nominal P3 `IN2` controls.
- offset **3** — `IN0` system controls (Start/Service/Coin).
- offset **120** changes in the provided recording but is NOT treated as a game button.

The initial exploratory mapping had mistakenly interchanged P1 and P2. The corrected parser uses the low/high split documented here. **This is an inferred byte layout, not independently verified original WolfMAME 0.106 serializer source**. Compatible playback must still confirm it.

## How to run (private machine only)

```bash
python3 tools/wolfmame0106_dino_input_reference.py \
  --inp /private/recordings/dino.inp \
  --wlf /private/recordings/dino.wlf \
  --out /private/analysis/wolfmame-dino-summary.json
```

The output contains aggregate input counts, possible alias patterns, and 20-second capture-window candidates. It does not export the original per-frame button stream. Do not commit even the output or derived commercial screenshots without reviewing provenance/licensing.

## Integrity and limitations

1. Reject malformed WLF version, wrong `dino` identifiers, mismatched four-byte recording tags, or an incompatible fixed record size.
2. Read only four candidate input byte offsets; count active-low press edges. Preserve separate nominal player names without asserting independent humans.
3. Compare suspicious input aliases: P1 attack versus P3 down, P1 jump versus P3 right, P1 down versus P2 jump, and P1 right versus P2 left. A keyboard or controller configuration can cause these relationships; without original playback they are not proof of game behavior.
4. Select up to twelve replay targets by dense P1 attack/jump press onsets. These are **not** confirmed levels, enemy spawns, game states or frame-exact visual matches.
5. Approximate elapsed times use 60 FPS. The actual game frequency, recorded frame scheduling and gameplay transitions must be verified in the matching emulator.

Run `python3 -m unittest discover -s tests -p 'test_wolfmame0106_dino_input_reference.py' -v` to test the parser using **synthetic** 124-byte records. No WolfMAME executable, Capcom ROM or original recording is required for those tests.

**Next research milestone:** execute the private INP in a matching WolfMAME 0.106 build using the owner's authorized ROM, record frame-indexed screenshots at candidate capture windows, confirm controller bindings and determine scene/level transitions. Until that happens, this is static input-record analysis, not a recovered Cadillacs and Dinosaurs game engine or emulation parity claim.

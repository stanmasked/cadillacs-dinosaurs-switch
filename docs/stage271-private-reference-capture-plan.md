# Stage 271 — two-tier private reference capture planning

A **reproducible, ROM-free** handoff from a Stage270 aggregate WolfMAME 0.106 input summary to candidate frame requests. This is preparation for actual reference footage, **not replay or proof of matching the arcade game**.

## Generate a candidate capture plan privately

```sh
python3 tools/wolfmame0106_dino_input_reference.py \
  --inp /private/recordings/dino.inp \
  --wlf /private/recordings/dino.wlf \
  --out /private/audits/inputs.json

python3 tools/wolfmame0106_reference_capture_plan.py \
  --summary /private/audits/inputs.json \
  --out /private/audits/capture-plan.json
```

The planner **does not open INP, WLF or any game ROM**, only the aggregate summary. It enforces Stage270's nominal player-port byte offsets, exact game/format witness and strictly unverified flags.

### Sampling strategy

- **Overview:** up to 12 nonoverlapping 1200-record intervals, sampled once every 60 recorded input frames (about one capture per second **if** the game's real frame rate is 60 FPS).
- **Detail:** every recorded input frame in the single 1200-record interval with the most P1 attack/jump onset events, useful for examining timing, animation and weapon interactions after *real* playback.
- The raw `requested_frames` values are indices in the INP. The emulator's screenshot clock may require a measured offset; do **not** silently assume frame-index identity.
- The JSON carries a SHA-256 over canonical Stage270 aggregate summary JSON to detect accidental plan/source mismatches.
- The planner refuses duplicate JSON keys, symlink inputs, wrong game names, reordered P1/P2 mapping, overlapping/unaligned windows, invalid dimensions or forged authenticity claims.

### Playback requirements and limitations

The original uploaded record declares WolfMAME **0.106**, not modern MAME 0.289. Official MAME 0.106 source and Windows binaries are archived by MAMEdev at https://www.mamedev.org/oldrel.html . Those official MAME builds and WolfMAME builds are not necessarily replay-compatible; **use the matching WolfMAME 0.106 release for actual INP replay**.

A historical 0.106 Windows CLI example is `mamep106-vc.exe dino -playback dino`. Old versions normally look in an `inp` folder and add the extension themselves. Versions/configurations may differ, and legacy keyboard/controller configuration can alter playback results. **No real WolfMAME playback has been completed in this PR.** A 20-second capture target is **not** an identified game stage or proof of identical content.

For local testing without proprietary input or a game ROM:

```sh
python3 -m unittest discover -s tests -p 'test_wolfmame0106_reference_capture_plan.py' -v
```

Keep the private INP/WLF, ROM, generated input summaries and actual screenshots/video **outside the public repository**. Store only source code, synthetic fixtures, and non-sensitive development notes here.

## Acceptance conditions before using captured footage as a benchmark

1. Matching WolfMAME executable version and actual game/ROM identification documented, with playback started at original beginning.
2. The game actually advances throughout the reference interval; captures are not a static title screen, desynced replay or incorrect input configuration.
3. Verify **frame alignment** between WolfMAME capture counter and recording index using an externally witnessed unique event; document any offset and dropped/duplicated captures.
4. Only then compare frame-indexed imagery, attack/sprite timing and enemy movements against equivalent explicit remake scenarios. Original sprites/ROM and derived captures remain private.

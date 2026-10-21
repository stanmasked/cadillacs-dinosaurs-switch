# Stage 272 — private WolfMAME 0.106 playback preflight

**Goal:** Before requesting 1,420 images from a complete ~87-minute legacy INP playback, first verify that the game starts and the capture counter can be reconciled with the saved input recording. This is a *preflight protocol*, not a completed replay.

## Generate a short bootstrap sample request

```sh
python3 tools/wolfmame0106_replay_preflight.py \
  --plan /private/audits/capture-plan.json \
  --start-anchor 102 \
  --out /private/audits/bootstrap-frames.json
```

Frame **102** was obtained from the private Stage270 analysis of the user's `dino.inp` (first *nominal* Start1 press). It is not proof that the original game started on exactly that emulator-video frame. The generated example requests 23 INP frame positions: fixed early probes at 0, 1, 2, 30, 60, 90, 119, 120, 180, 300, 600, 900, 1800 and 3600; plus 9 positions around the Start1 input onset. At 60 input records per second this covers nominally the first minute, not the entire playthrough. **Actual WolfMAME video frame alignment must be measured**, not inferred from the file name.

This tool reads the Stage271 aggregate plan only. It never opens or distributes the original ROM, INP, WLF or game imagery.

## Integrity audit *after private playback*

Capture the requested positions in a matching WolfMAME 0.106 build with a user-authorized, locally held `dino` ROM. Store screenshots **privately**, named `frame-00000102.png` etc. Then:

```sh
python3 tools/wolfmame0106_replay_preflight.py \
  --plan /private/audits/capture-plan.json \
  --start-anchor 102 \
  --captures /private/audits/screenshots \
  --out /private/audits/bootstrap-png-receipt.json
```

The capture auditor checks the *exact requested PNG filename set*, rejects symlinked files, validates PNG signature, chunk boundaries/CRCs, DEFLATE stream integrity and bounded IHDR geometry; records dimensions, color type and SHA-256 for each file. Use optional `--width` and `--height` **only after measuring** the actual emulator capture layout.

**Critical provenance limitation:** This receipt authenticates bytes of the files actually supplied; it cannot prove that the files came from WolfMAME, correspond to those input indices, contain Capcom game pixels, show successful gameplay, or agree with the native Nintendo Switch renderer. To establish input→video synchronization, separately observe a distinctive Start1/game response with exact emulator frame IDs and document any offset, dropped frames or duplicates.

All screenshots, the original input stream, user ROM and any capture receipt describing actual commercial imagery **stay off public GitHub**. Only ROM-free source and synthetic tests are committed.

## Test and integration

```sh
python3 -m unittest discover -s tests -p 'test_wolfmame0106_replay_preflight.py' -v
```

These 11 synthetic tests are not original-game execution tests. Stage272 is stacked on Draft PR #79. Its CI completion does not replace upstream NeXium paired guest gates nor any physical Switch verification.

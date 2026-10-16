# Stage 29 — inspect MAME full-frame motion before trusting a capture window

The existing capture pipeline validates six streams from one MAME video
render callback, and now checks the frame-to-frame evidence as well.
This **does not** automatically identify first-level gameplay.

## Why this matters

MAME input recordings may desynchronize (see MAME's
`src/emu/ioport.cpp`, `ioport_manager::playback_end`). A MAME process
can terminate without a nonzero error code when recorded input diverges,
and a formally complete frame dump could still be from attract mode.

Motion alone is similarly insufficient evidence: title-screen animations
and demo scenes also move. The new report therefore **always** says
`first_level_verified: false` and `input_replay_synchronized: false`.

## Independent private capture audit

```sh
python3 tools/mame_capture_motion_audit.py /private/cps1-capture \
  --first 900 --count 36 --report /private/cps1-motion-report.json
```

Optionally set `--stride 2` to explicitly inspect alternate MAME frames,
without pretending skipped frames were captured.

For every consecutive selected pair of **384×224** MAME reference RGB
images, the tool measures:

- exact number of RGB pixels whose bytes changed;
- per-channel number of changed pixels and total absolute byte error;
- first changed pixel coordinate and inclusive change rectangle;
- which of the six independent raw streams changed (RGB24, effective
  palette, buffered OBJ, gfx RAM, CPS-A and CPS-B);
- complete SHA-256 of all six private streams, **without placing their
  contents** in the JSON report.

It summarizes the number of unique streams, unchanged transitions,
longest unchanged transition run and a warning for an entirely static
multi-frame reference window. A static screen is a *diagnostic warning*,
not an automatic claim of a failed capture or an invalid game state.

The tool validates the MAME render-pass manifest identity, full viewport,
same-pass buffered OBJ, byte order, effective palette provenance and
all binary stream lengths, and refuses missing/incomplete frames.
Existing reports will not be overwritten.

## Integration with existing local MAME runner

`tools/mame_local_capture_run.py` in the stacked parent PR now includes
a `sequence_motion_diagnostic` in its report after successfully
validating all requested frame streams. An additional field,
`first_level_verified: false`, makes it impossible to confuse valid
dump *format* with confirmed real first-level gameplay.

**Review dependencies:** this branch stacks on PR #13 (local capture
runner), which stacks on PR #12 (ROM audit). The actual render callback
patch remains in PR #8, and capture-to-Switch playback converter in
PR #11. No PR in this stack should be merged before validating its
parent and a working CI.

## Automated tests

```sh
python3 -m unittest discover -s tests -p 'test_mame_capture_motion_audit.py' -v
```

10 standalone ROM-free cases exercise frozen RGB with moving OBJ,
one-pixel changes, coordinates and channel errors, missing/truncated
data, manifest validation, one-frame windows, decimation, bad input
ranges, and no-overwrite output. An eleventh new integration case
asserts that the synthetic MAME stand-in adds motion information but
does not claim authentic level entry.

These tests exercise **synthetic data only**. The actual `dino` game
has not been captured live in this environment, so no real first-level
picture, MAME pixel-perfect parity or Nintendo Switch runtime result
is asserted.

Source references:

- MAME input lifecycle:
  https://github.com/mamedev/mame/blob/master/src/emu/ioport.cpp
- MAME input replay/exit:
  https://docs.mamedev.org/commandline/commandline-all.html

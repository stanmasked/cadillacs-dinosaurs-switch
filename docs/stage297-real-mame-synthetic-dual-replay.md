# Stage297 — two actual MAME 0.106 synthetic replay windows

The preceding Stage296 confirmed that source-pinned historical MAME 0.106
ran an original **artificial Minivader Z80** program, recorded/replayed
artificial input, produced a real MNG, and decoded all 24 frames with
24 per-frame input-read counter rows (callback indices 10–33).

This stage tests **repeatability across two distinct real MAME replay
processes**, using *only the synthetic recording* from a third, actual
MAME process. This is not original Cadillacs and Dinosaurs playback.

## First real run and source-grounded correction

Initial [Windows CI #39671227200](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39671227200) **correctly failed** with:
- 16/16 matching decoded overlapping pixels;
- 16/16 matching port-0 counters and 16/16 matching input-word counters;
- input counters advanced, **but video pixels were static**.

The original artificial Z80 fixture wrote to address `0xa000`. In the
historical source `src/vidhrdw/minivadr.c:minivadr_videoram_w`, the
screen row equals `(address - 0xa000) / 32`. The driver `src/drivers/minivadr.c`
defines **visible y=16..240**, so address `0xa000` maps to **invisible
y=0**. The screenshot never changed despite the Z80 modifying RAM.

The fixture now writes to **`0xa200`**, which maps to visible **row y=16**,
without changing the strict non-static test condition. A new unit test
guards against inadvertently writing outside the visible area again.
This remains an entirely invented, temporary ROM and the resulting
Windows CI outcome must be independently rechecked.

## Windows CI protocol

Within the existing Stage295 **short-lived test-only MAME** built after
the production code-only artifact has already been uploaded:

1. Verify the synthetic ROM through the real MAME ROM loader.
2. Invoke real MAME once with `-record stage297` to write 48
   frames of synthetic Minivader input in a temporary workspace.
3. Start a fresh real MAME replay process for the callback range
   **[10,34)**, requesting 24 MNG frames and 24 input-read counter rows.
4. Start another fresh MAME replay process using the **same synthetic INP**
   for callback range **[18,42)**, also requesting 24 MNG frames and rows.
   Before this second run, remove the first run's CSV from the temporary
   workspace to prevent a stale first-run log being mistaken for output
   from the second process. Unique MNG base names keep video files separate.
5. Independently decode each actual MNG using the Stage296 corrected
   packed indexed 1/2/4/8-bit PNG verifier and normalizer. Build ephemeral
   SHA-256 digests of RGBA pixel bytes *in memory only*.
6. Validate each numeric CSV's exact index sequence, bounds, layout,
   nondecreasing counters and exact 24-row count.
7. Compare the **16 shared absolute callback indices 18–33**,
   not similarly numbered rows in separate windows. Record only bounded
   aggregate match/mismatch counts for normalized pixels, first-port
   successful reads and total input words read.
8. A positive result requires 16/16 matching normalized images,
   16/16 matching port-0 read counts and 16/16 matching total word counts,
   **with changing pixels and advancing counters in the overlap**.
   An identical but completely static video or read counter sequence
   is not acceptable as positive repeatability evidence.
9. Emit one JSON summary with status, aggregate counts and explicit
   **false authenticity, original-game and Switch parity flags**.
   All synthetic ROM, modified test executable, INP, MNG, CSV and frame
   digest data are discarded in a temporary working directory. Do not
   upload, commit or attach them to PRs.

The production ROM-free MAME artifact remains separate and is uploaded
before temporary Minivader patching; this stage does not replace it.

## Outcomes

- `SYNTHETIC_REAL_MAME_DUAL_REPLAY_MATCH_UNAUTHENTICATED` —
  two separate MAME replay processes agree across 16 changing frames
  and advancing input-read counters.
- `SYNTHETIC_REAL_MAME_DUAL_REPLAY_DIVERGED` —
  pixels and/or the successful read counts differ on shared callbacks.
- `SYNTHETIC_REAL_MAME_OVERLAP_STATIC_VIDEO` —
  agreement exists but at least one compared stream is static.
- `BLOCKED_SYNTHETIC_*` — earlier ROM, recording, replay,
  trace or MNG audit failed, so no equality is claimed.

Unlike Stage295/296's preliminary ROM-loader smoke gate, **Stage297's
dual-window comparison is mandatory** for Windows CI to pass.

## Python synthetic unit tests

    python -m unittest discover -s tests -p 'test_mame0106_synthetic_dual_replay_297.py' -v

The pure unit tests cover candidate matches, a single diverging pixel,
individual port/word mismatches, static streams, incorrect absolute
callback alignment, malformed CSV/unsafe symlinks and the fail-closed
real-child-process orchestration contract with simulated process results.

## Verification limits

A fully passing Windows run establishes repeatability **only for this
invented Minivader fixture**. It does not attest independent WolfMAME
binary provenance, exact causal mapping from an input record to a video
callback, original Cadillacs and Dinosaurs gameplay, sprite/palette
parity, or a real Nintendo Switch console. The original user-provided
dino ROM, dino.inp and dino.wlf still require private local playback
outside GitHub.

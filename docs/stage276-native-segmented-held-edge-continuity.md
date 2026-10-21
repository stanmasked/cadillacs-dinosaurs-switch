# Stage 276 — retain input-edge continuity across independent native training rounds

Stage275 deliberately resets the original ROM-free training arena every 1200 input records so that a synthetic opponent defeat in one round cannot eliminate combat coverage in subsequent rounds. However, the first input of every reset round was incorrectly treated as a *new* attack or jump edge whenever the player was already holding that button.

This stage fixes the **input interpretation without changing the independent training-state reset**. The native Stage274 stdin harness now supports an optional validated `--prior-active-low=HH` two-digit hexadecimal P1 byte. It initializes the **previous-held input bitmask** from this byte before processing the first record, without injecting an additional simulation tick or carrying forward combat state. If omitted, the option defaults to `ff` (all buttons released), preserving legacy standalone execution.

For each round `i`, the private Stage275 driver passes the immediately preceding input byte `stream[i-1]`; the very first round uses `ff`. At every round it therefore distinguishes:

- **Held through the boundary:** not a new press.
- **Released → pressed at the boundary:** a genuine new press.
- **Released throughout:** no event.

The Python driver independently scans the *unsplit* nominal P1 stream and fails if the sum of native C press-edge counters differs in either training mode, regardless of compiler or chosen round length. Only aggregate counts are reported.

## Private evidence on the user-provided 0.106 dino recording

All **314,951** nominal P1 input records were analyzed, keeping the source INP/WLF, ROM and full P1 stream outside GitHub.

| Metric | Naively reset 1,200-frame rounds | Continuity-corrected |
|---|---:|---:|
| Attack press onsets | 7,486 | **7,455** |
| Jump press onsets | 1,525 | **1,516** |
| Synthetic added boundary attack presses | 31 | **0** |
| Synthetic added boundary jump presses | 9 | **0** |

Original cross-boundary new presses remain correctly counted (four attack edges and two jump edges happened exactly on 1200-record boundaries). This only validates the nominal active-low byte stream; it does **not** verify the WolfMAME 0.106 playback mapping or original arcade combat.

## ROM-free CI

```sh
python3 -m unittest discover -s tests -p 'test_dino_native_round_held_edge_continuity.py' -v
```

Eight synthetic tests cover pressed buttons surviving boundaries, truly new presses at boundaries, simultaneous held attack/jump, several segmentation lengths, valid and invalid two-digit hexadecimal seeds, original default behavior and compiler parity when Clang exists. The existing Stage274/275 native tests remain in the same CI suite.

**Limitations:** The arena still resets health, position, target and invented sparring state every round; this test does not establish original game accuracy or visual-frame synchronization. The user-owned INP/WLF, ROM and game-derived image data are never added to public GitHub.

This stage is stacked on Draft PR #83. No original-game bytes are included in sources, fixtures, docs or test data.

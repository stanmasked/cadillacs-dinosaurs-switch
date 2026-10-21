# Stage298 — private, activity-guided dino INP capture windows

## Why

Stage297 proved two independently launched historical MAME 0.106 synthetic
Minivader replays matched 16/16 **dynamic** shared video frames and both
input-read counters. This does not prove playback of the original
Cadillacs and Dinosaurs ROM or `dino.inp`.

The original assets cannot currently be mounted into the development
environment. Do not upload ROMs, INP, WLF, screenshots, decoded frames,
private SHA-256 values or receipts to the public GitHub repository.

Stage292 private dual-capture tooling already exists, but its default
window starts at callback index **36,000**. That arbitrary location may
be outside shorter recordings or show no player activity. Stage298 adds
an **opt-in, private activity-based selector** to choose two overlapping
candidate capture windows from local source-inferred INP press onsets.

## What Stage298 actually changes

`tools/wolfmame0106_private_active_window_298.py` validates a local
dino INP/WLF pair using the existing exact 0.106-family structural reader
(32-byte header, 124-byte input records, 598-byte WLF companion), and
stream-scans active-low transitions **high→low** in the inferred CPS-1
player 1 and player 2 input port positions.

- P1/P2 direction press transitions: score 1 each.
- P1/P2 attack and jump press transitions: score 4 each.
- Start1: score 2.

These weights are **only selection heuristics**, not controller
verification, latency or gameplay scoring. Their inferred source bytes
were derived from upstream MAME 0.106/CPS-1, not an independently
authenticated WolfMAME binary.

The selector evaluates candidate *common* video windows with a bounded
deque and chooses the earliest highest-scoring window that contains
at least the requested number of distinct press onsets. It enforces
both windows fit the structurally reported number of recording frames.
Memory for the sliding window is O(overlap length), not O(recording length).
The scan occurs only on private ordinary files outside the repository;
the original button values, full event timeline and SHA-256 bytes never
appear in the aggregate final report.

## Local-only command

Use a private Windows machine with the **authorized original dino ROM**,
paired original INP/WLF and the source-pinned, instrumented Windows
MAME executable. The input files must remain outside the repository:

~~~bat
python tools\wolfmame0106_private_two_window_experiment.py ^
  --runtime-bundle C:\private\mame290-bundle ^
  --emulator C:\private\mame290-bundle\mame0106.exe ^
  --rom-dir C:\private\roms ^
  --inp C:\private\recordings\dino.inp ^
  --wlf C:\private\recordings\dino.wlf ^
  --out-dir C:\private\audits\experiment-298-a ^
  --auto-window --frames 1200 --shift 600 --minimum-edges 3 ^
  --seconds 1800
~~~

Omit `--auto-window` to retain the previous explicit
`--first-start` behavior. In automatic mode the arbitrary
manual start index is **ignored**, and the locally inferred source
activity determines the first callback index.

The coordinator writes its previous seven private files only when a
plausible window is found:

- two separate MNGs;
- two Stage290 count CSVs;
- two private SHA-bound capture receipts;
- one aggregate-only Stage292 summary.

The summary adds:

- `window_selection_strategy` —
  `source_inferred_local_inp` or `manual`;
- `source_inferred_overlap_press_onsets` —
  aggregate press transition count within the common window;
- `wolfmame_input_signal_mapping_independently_verified=false`.

If the input pair is invalid, the recording is too short, no candidate
window contains enough transitions, or selection returns invalid data,
the private experiment aborts **before creating output files or
launching an emulator**.

## Limitations

Auto-selection locates *hypothesized input activity*, not a
gameplay-verified interval. Callback indices are not independently
proven to correspond one-to-one with INP record numbers.

The existing Stage291 cross-run requirement still applies: two
separate candidate MNGs and input-read traces must agree on **dynamic**
shared video pixels and advancing counters, and both must be privately
bound to the same content fingerprints.

No result from source heuristics or synthetic CI can claim original
dino gameplay, WolfMAME-specific serializer authenticity, independent
record-to-callback synchronization, visual/audio parity or physical
Nintendo Switch execution.

## Public ROM-free CI

~~~sh
python -m unittest discover -s tests -p 'test_wolfmame0106_private_active_window_298.py' -v
~~~

All fixtures are generated dummy INP/WLF records. Tests cover weighted
P1/P2 press onsets, fixed held buttons, source/stride tampering, unsafe
symlinks, insufficient transitions, invalid window boundaries,
fail-closed integration before process launch, manual compatibility,
and sanitized aggregate reports.

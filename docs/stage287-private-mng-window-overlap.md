# Stage287 — private MNG capture-window overlap check

This stage adds a **local-only** comparison of two candidate MNG videos from
the Stage286 bounded capture runner. It compares two overlapping, explicitly
requested callback-frame windows and detects whether decoded **pixels** in
the overlap agree. The comparator does not export images, frame hashes,
individual input records, private paths, ROM files, INP or WLF.

The comparison can detect capture instability, inconsistent frame numbering or
non-deterministic output between two candidate videos. It **cannot** prove
independent emulator executions, WolfMAME provenance, INP-to-video alignment,
the source of the imagery or gameplay parity with the original arcade game.

## Private capture procedure (no game assets in GitHub)

Use the same authorized, private dino ROM directory and paired original
`dino.inp` / `dino.wlf`, and the ROM-free Stage286 custom-patched MAME 0.106
executable. In a private Windows terminal, record two separate windows:

```bat
python tools\wolfmame0106_private_mng_capture.py ^
  --emulator C:\private\mame0106.exe --rom-dir C:\private\roms ^
  --inp C:\private\recordings\dino.inp --wlf C:\private\recordings\dino.wlf ^
  --start-frame 36000 --frames 1200 --seconds 1800 ^
  --capture-out C:\private\audits\window-a.mng ^
  --out C:\private\audits\window-a.json

python tools\wolfmame0106_private_mng_capture.py ^
  --emulator C:\private\mame0106.exe --rom-dir C:\private\roms ^
  --inp C:\private\recordings\dino.inp --wlf C:\private\recordings\dino.wlf ^
  --start-frame 36600 --frames 1200 --seconds 1800 ^
  --capture-out C:\private\audits\window-b.mng ^
  --out C:\private\audits\window-b.json
```

Both captures emulate the recording from the beginning but retain different
bounded MNG windows. These examples overlap for 600 callback indices
(36600–37199 inclusive); both capture runs must first finish with clean exits,
the requested frame counts and structurally valid MNGs. Do not compare
unsuccessful receipts as proof of gameplay.

Compare the saved private MNG files:

```bat
python tools\wolfmame0106_private_window_overlap.py ^
  --first-mng C:\private\audits\window-a.mng --first-start 36000 ^
  --second-mng C:\private\audits\window-b.mng --second-start 36600 ^
  --min-overlap 16 --out C:\private\audits\stage287-overlap.json
```

The comparator audits both MNG containers and embedded PNGs, normalizes pixel
modes/PNG filters, hashes normalized decoded pixels **only in process
memory**, then compares the overlapping positions. The private JSON receipt
contains counts, an optional first mismatching callback index and
conservative provenance flags; it contains no frame digests or file paths.

The output is one of:

- `OVERLAP_MATCH_DYNAMIC_UNAUTHENTICATED`: every overlapping pixel frame
  matches and at least one adjacent frame changes; CLI exit code 0.
- `OVERLAP_MATCH_STATIC_UNAUTHENTICATED`: matching but all overlapping frames
  are identical to their neighbors, offering weak evidence; CLI exit code 2.
- `OVERLAP_PIXEL_MISMATCH_UNAUTHENTICATED`: one or more overlapping frames
  disagree; CLI exit code 2.
- `INSUFFICIENT_REQUESTED_WINDOW_OVERLAP` or
  `INCOMPATIBLE_CANDIDATE_MNG_LAYOUT`: non-comparable capture windows;
  CLI exit code 2.
- `BLOCKED_PRIVATE_OVERLAP_COMPARISON`: malformed or unsafe inputs;
  CLI exit code 2.

Only distinct private, regular, non-symlink MNG files are allowed, with the
existing auditor's 512 MiB input and 3601-frame limits. The receipt must be a
new private JSON file outside the repository. Never upload the two MNGs or
the original recording/ROM data to public Actions.

Even a dynamic exact match only demonstrates **two supplied candidate videos
agree** on decoded pixels at the declared callback offsets. A later separate
input/video alignment experiment is required to substantiate a timing mapping.
Physical Nintendo Switch gameplay remains untested by this check.

## ROM-free CI

```sh
python -m unittest discover -s tests -p 'test_wolfmame0106_private_window_overlap.py' -v
```

The tests construct tiny synthetic MNG/PNG data and exercise mismatches,
static runs, offset bounds, malformed files, private-only receipts, and
conservative result statuses. Neither real dino footage nor a ROM is used.

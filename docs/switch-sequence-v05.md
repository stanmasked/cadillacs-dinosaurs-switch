# Nintendo Switch v0.5 — bounded native frame-sequence replay

This is a **technical animation inspector**, not gameplay emulation or an
HD graphics restoration. It displays consecutive CPS-1 **RAM snapshots**
using the native C renderer, with a deterministic 60 Hz timebase.

## Private SD-card inputs

```text
switch/cadillacs-dinosaurs-switch/
  cadillacs-dinosaurs-switch.nro
  gfx.bin          4,194,304 bytes; assembled privately from your own dino.zip
  sequence.bin      optional versioned timeline of 1..120 CPS1SCN1 scenes
  scene.bin         optional older static snapshot, fallback when no valid sequence
```

**No ROMs, extracted graphics, palettes or real game snapshots are committed
to GitHub.** A provided sequence may itself contain copyrighted derived
graphics/state, so it belongs in private storage.

Use the existing tools to create full-color `CPS1SCN1` frames with
an *effective* captured 3072-color palette. Then place a directory of
named JSON snapshots (`0000.json`, `0001.json`, etc.) on your computer:

```sh
python3 tools/cps1_sequence_export.py \
  --frames-dir /private/cps1-captures --fps 12 \
  --out /private/sequence.bin
```

For a deterministic test **without running MAME**, you can generate
24 **artificial** motion frames (sprite positions / background registers,
not actual original animations):

```sh
python3 tools/cps1_sequence_export.py --demo --fps 12 \
  --out /private/sequence.bin
```

### File format CPS1SEQ1

The file starts with a strict 20-byte, little-endian header:

| Offset | Size | Field |
|---|---:|---|
| 0 | 8 | ASCII `CPS1SEQ1` |
| 8 | 2 | Number of frames 1..120 |
| 10 | 2 | Source FPS 1..60 |
| 12 | 4 | CRC32 (IEEE) of all following scene files |
| 16 | 4 | Reserved, must be zero |
| 20 | N × 62,510 | Unmodified `CPS1SCN1` scene blobs |

The maximum accepted file size is **7,501,220 bytes**. On load,
the native decoder validates the outer length and CRC32, followed by
each embedded frame's magic, length, own CRC32, and reserved byte.
The bounded file is held in memory, so changing it on SD during
playback is unsupported.

Playback is based on real system ticks converted to a virtual 60 Hz
clock (via libnx `armGetSystemTick` / `armTicksToNs`) rather than
counting display iterations. Speed choices: 0.5×, 1×, 2×. After
a pause or single-frame step, playback remains paused until resumed.

### Switch controls when sequence.bin is valid

| Button | Function |
|---|---|
| A | Pause / resume |
| B | Next frame (and pause) |
| Y | Previous frame (and pause) |
| L / R | Decrease / increase playback speed |
| X | Switch to tile inspector and back |
| PLUS | Exit |

When no valid sequence is present, **v0.4 behavior is retained**:
view a single `scene.bin` with D-pad background panning, ZR fast-pan,
A reset, or just inspect 16×16 tiles with no snapshots.

## Verification

`tests/test_cps1_sequence.py` links the **same C source** used on
Switch into a host shared library, then tests CRC validation, embedded
scene extraction, size bounds, 60 Hz playback accumulation, wraparound,
pause/step/speed controls and lack of mutation of the supplied buffer.
The exporter creates only synthetic test frames.

Limitations: MAME runtime state capture has not been achieved. Synthetic
timeline animation only tests the **rendering and playback pipeline**:
there is no player control, combat, sound, native HD art, frame-accurate
arcade emulation, or physical Switch hardware validation.

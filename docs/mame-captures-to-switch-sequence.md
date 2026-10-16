# Stage 24 — Import genuine MAME render captures into the Switch timeline

**Purpose:** bridge a completed sequence of *actual MAME* CPS-1 render
callbacks to the existing native Switch v0.5 viewer. The imported captures
contain the SAME-pass reference RGB, effective palette, CPS-A/B registers,
192 KiB GFX RAM and the VBlank-latched 0x800-byte OBJ buffer.

The code is in a **stacked PR on top of the experimental render-capture
PR #8**. PR #8 must be validated/merged first. This module does not
contain, redistribute or extract game ROMs.

## 1. Capture frames inside your private copy of instrumented MAME

Following [MAME render-pass capture instructions](mame-render-pass-capture.md),
create a capture output directory and install the opt-in source patch into
your own MAME checkout.

For example, for 36 sequential frames beginning at MAME frame 900:

```sh
mkdir -p /private/cps1-captures
export CPS1_RENDER_DUMP_DIR=/private/cps1-captures
export CPS1_RENDER_DUMP_START=900
export CPS1_RENDER_DUMP_COUNT=36
/path/to/instrumented/mame dino -rompath /private/roms
```

Only **full** `screen_update_cps1` callbacks yield a committed capture.
The collector will refuse to produce a full-frame manifest for partial
raster updates. It never overwrites a previously committed capture.

These instructions assume you have legally held original game ROMs.
Captured graphics, state, RGB and palette are private copyrighted game
content: do not upload them to GitHub.

## 2. Convert only verified-format complete frames

```sh
python3 tools/mame_capture_sequence.py /private/cps1-captures \
  --first-frame 900 --count 36 --fps 60 \
  --out-dir /private/dino-real-sequence
```

This creates:

- `sequence.bin` in the native `CPS1SEQ1` format; each individual
  frame is a checksum-validated `CPS1SCN1` blob, including the effective
  palette and **latched** OBJ.
- `sequence-provenance.json`: explicit frame numbers, hashes for all
  six streams and original manifest per frame, SHA-256 for every packed
  scene blob and for the outer timeline, frame-selection metadata,
  and explicit **not verified** fidelity flags.

The JSON report contains hashes but **no raw sprite pixels or memory**.

For decimation, opt in explicitly with `--stride 2`. The exporter never
fills gaps, invents missing frames or falsely renumbers them as consecutive
MAME captures. Counts are limited to 1–120, and the playback rate must
be 1–60 FPS. The `--fps` flag controls the viewer only; it does not
assert a physically exact MAME frame clock.

Incomplete OBJ, invalid dimensions, missing/bad manifests, truncated
RAM/palette, out-of-range memory windows, missing frame numbers, or
false `pixel_parity_verified=true` are rejected before output creation.

## 3. Copy to Switch v0.5

Copy the generated `sequence.bin` to:

```text
sdmc:/switch/cadillacs-dinosaurs-switch/sequence.bin
```

This is read by the **existing v0.5 viewer** alongside your own
`gfx.bin` (exactly 4,194,304 bytes, created privately from the
original game ROM). No newer NRO is required for this binary format.

Controls: A pause, B/Y next/previous, L/R playback speed, X tiles/scene.
The existing native renderer is a partial CPS-1 renderer. This tool
does not add CPU emulation, controls for the original four characters,
enemy AI, combat, music, or actual game logic.

## Verification and current limitation

```sh
python3 -m unittest tests.test_mame_capture_sequence -v
```

Eleven ROM-free integration tests verify 1–3 frame export, inner/outer
CRCs, strict ordering and stride, cryptographic provenance, full OBJ,
manifest validation, CLI and no-overwrite/partial-output behavior.

**Actual MAME playback is still unavailable in the development
environment**: the emulator is not installed, and direct package
downloads could not be completed because network access is unavailable.
We cannot claim a real first-level capture, a correct camera/level map,
a pixel-exact reconstructed frame or physical Switch validation.

This work puts the last conversion stage in place, ready to ingest real
first-level captures as soon as instrumented MAME can execute.

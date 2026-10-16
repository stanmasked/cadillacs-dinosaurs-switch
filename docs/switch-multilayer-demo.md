# Switch v0.5 — CPS-1 multilayer diagnostic sequence (Stage 23)

The existing native Switch v0.5 NRO already supports `CPS1SEQ1`
timelines from `sdmc:/switch/cadillacs-dinosaurs-switch/sequence.bin`.
This stage adds a deterministic **36-frame, 12 FPS** sequence generator
with more complete, *synthetic* graphics composition. No new NRO required.

## What it exercises

- Three populated 64×64 CPS-1 scroll maps with MAME-compatible
  Scroll1 8×8, Scroll2 16×16 and Scroll3 32×32 tile addressing.
- The 384×224 CPS-1 hardware viewport at physical raster X 64..447,
  Y 16..239, drawn by the existing native renderer.
- Independent background motion: Scroll1 +4 pixels/frame, Scroll2 +2,
  Scroll3 +1 every 3 frames.
- Hardware-style `video_control=0x0d` enabling all scroll layers plus
  **per-scanline Scroll2 rowscroll** (1,024 word table).
- Three synthetic moving sprite entities (2×2, 1×1, 2×1 tiles), including
  flip-X phase and a CPS-1 end-of-list marker.
- A static **synthetic** effective RGB palette with 3,072 entries;
  this is *not* the original game's palette.

**Crucial limitation:** this is not the original first level, enemy AI,
collision, actual gameplay, correct animation or faithful stage geometry.
The console reads graphics only from the user's local legally held
`gfx.bin`. Tile placements and movement are a deterministic visual
fixture, not ROM-derived game state. No ROM, art or frames are committed
to GitHub.

## Create the sequence

From the repository root:

```sh
python3 tools/cps1_layered_demo.py \
  --frames 36 --fps 12 \
  --out local_output/sequence.bin \
  --report local_output/sequence-report.json
```

The generator refuses existing output paths, produces `CPS1SEQ1`
bytes with individual `CPS1SCN1` CRC32 checksums and an outer timeline
CRC32, and emits an explicit `authentic_gameplay: false` report.

The standard 36-frame sequence is exactly **2,250,380 bytes**.
Additional validated configurations accept 1..120 frames and FPS 1..60.

For a private installation using the previously confirmed v0.5 NRO,
copy `sequence.bin` into:

```text
sdmc:/switch/cadillacs-dinosaurs-switch/sequence.bin
```

Keep the existing `gfx.bin` in that same folder (exactly 4 MiB).
Launch the existing `cadillacs-dinosaurs-switch.nro` from Homebrew Menu.
The viewer will prefer the sequence to a static `scene.bin`.

Controls: A pause, B/Y next/previous frame, L/R adjust speed,
X toggle tiles/scene, PLUS exit.

## Validation

```sh
python3 -m unittest tests.test_cps1_layered_demo -v
```

Seven ROM-free regression tests check full tile-index permutation,
palette bounds, three scrolling layers, per-line rowscroll, OBJ markers,
scene/timeline headers and CRC32, frame-to-frame RGB differences and
the safe no-overwrite CLI.

An independent local render using the user's privately supplied 4 MiB
graphics region generated 384×224 reference previews of frames 0, 18
and 35. These images are genuine **graphics ROM pixels**, but the
scene layout and palette are not original game content.

This test is independent of the open MAME-render capture PRs. No real
MAME game frame, CPS-1 gameplay logic or physical Switch test is claimed.

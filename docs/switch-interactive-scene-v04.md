# CPS-1 Switch v0.4 — interactive scene inspection

Native Switch can now redraw a **single captured CPS-1 scene** while a
developer pans the three tilemap scroll registers in real time. It still
does not execute original game code, animate characters, run AI, or emulate
camera scripting.

## Using the viewer

On an SD card, keep the same files as v0.3:

```text
switch/cadillacs-dinosaurs-switch/
  cadillacs-dinosaurs-switch.nro
  gfx.bin          # private, user-assembled 4 MiB dino graphics region
  scene.bin        # optional versioned, CRC32-protected, single-frame RAM capture
```

Switch's 1280×720 screen renders a 384×224 CPS-1 scene at a crisp integer 3×.
The binary `scene.bin` format is **unchanged** from v0.3. The old v0.3
captures remain usable.

| Input in scene view | Function |
| --- | --- |
| X | Toggle scene / indexed-tile inspector |
| D-pad | Move the background sampling coordinates |
| Hold ZR + D-pad | Pan background faster |
| A | Restore original CPS-A X/Y scroll offsets from capture |
| PLUS | Return to Homebrew Menu |

Controls in the tile inspector are unchanged (D-pad/L/R page navigation,
A grayscale inversion, B transparency preview, Y grid).

The camera operation moves **all three** captured scroll X/Y registers,
wrapping modulo 0x10000 like hardware register writes. In a static snapshot
sprites retain their recorded on-screen positions while backgrounds move.
That distinction is deliberate; actual CPS-1 sprite placement and gameplay
camera logic need synchronized game runtime state.

## Correctness and performance

- Portable C function `cps1_scene_pan()` makes scroll offsets deterministic.
- Redraw occurs only when a directional input actually changes the camera or
  when A resets it. When no scene is present, the tile inspector still works.
- Same native C engine used on Switch is linked into host tests (no ROM).
- Unit tests assert 16-bit wraparound, reversible movement and pixel-for-pixel
  matching of native and Python renderers after a background camera shift.
- Workflow tracks `source/cps1_scene.c` and `source/cps1_scene.h` changes,
  so regressions in the C compositor cannot silently skip Python/C parity CI.

## Known limitations

Interactive scene panning is **diagnostic, not playable**. Real dino backgrounds,
animations and level geometry depend on actual RAM state, game execution and
frame-accurate reference capture. The ROM alone does not contain a coherent
runtime tilemap and effective palette. Captured states are not published.

The program uses a CPU software framebuffer, which may be slower than a GPU
renderer during scrolling. Frame-rate and memory use on real hardware remain
to be measured. This feature does not establish genuine HD-restored graphics.

See also [v0.3 capture/snapshot format](switch-native-scene-v03.md).

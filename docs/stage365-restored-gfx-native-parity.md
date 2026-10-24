# Stage365: verify restored private CPS-1 graphics in the native tile decoder

This diagnostic bridges private Drive recovery of a user-held CPS-1 graphics
region (Stage364) to the **actual C source file** compiled for Nintendo
Switch. It does not load a MAME game, reconstruct real CPS-1 palette RAM,
create authentic gameplay frames or certify physical hardware output.

The public tool `tools/cps1_private_restored_native_parity.py` requires a
private, **already-restored** `graphics-region-4MiB.bin`, its externally
pinned SHA-256, and separately pinned SHA-256 hashes for the portable
`source/cps1_tile.c` / `.h` pair. It rejects missing, symlinked, misplaced,
truncated and changed source graphics; it also rejects invocation in public
GitHub Actions before opening any private graphics bytes.

After verifying all pins, the tool compiles exactly the repository C tile
decoder with strict host GCC flags in a disposable directory, then compares
its 4bpp palette **indices** against an independent Python planar reader:

- Scroll1: 8×8 left and right halves
- Scroll2: 16×16
- Scroll3: 32×32

Per-layout samples include beginning/end tile codes, bank boundaries and
fixed-seed selections, with a default of 1,024 tiles per layout. It also
checks the native decoder rejects the first out-of-range code. The report
contains only aggregate counts, boolean validation flags and status; it
never includes original graphics bytes, actual pixel streams, content hashes,
private absolute paths, palette data or screenshots.

Run only in an owner-controlled private environment, outside GitHub Actions:

```sh
python3 -m tools.cps1_private_restored_native_parity \
  --gfx <PRIVATE_RESTORED_GRAPHICS_REGION> \
  --gfx-sha256 <PRIVATE_PINNED_GFX_SHA256> \
  --native-sha256 <PINNED_PUBLIC_C_SOURCE_SHA256> \
  --native-header-sha256 <PINNED_PUBLIC_H_SOURCE_SHA256> \
  --samples 1024 --out <NEW_PRIVATE_REPORT_PATH>
```

The report destination must be a new path outside the public source tree.
Preserve it in the private owner-only Google Drive evidence archive; preserve
the original graphics backup and source images separately without replacing
them.

On the actual private Stage364-restored GFX region, the independent C/Python
comparison passed 4,096 tile codes and **1,441,792** indices, with **zero**
mismatching tiles and all four layouts exhibiting 16 unique 4-bit indices.
Invalid native tile codes were rejected. Thirteen synthetic-only unittests
passed with `GITHUB_ACTIONS=true`, including deliberate Python-reference
poisoning that the differential test correctly classified as failure.

This is a graphics decoder consistency milestone, **not** an actual
historical MAME `-verifyroms dino` result and **not** playback of `dino.inp`.
A native Windows runtime and original frame-state capture are still needed
for actual game/video parity.
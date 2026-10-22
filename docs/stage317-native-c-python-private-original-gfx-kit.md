# Stage317 — complete public-source-only native C/Python private scene kit

## Reason for this stage

Stage315's public code ZIP contained Python helpers only. A genuine
private invocation of Stage305's native scene comparator requires the
actual Switch source files `source/cps1_scene.c` and
`source/cps1_tile.c`, with their public headers. Without them the
private source-verified ROM still passes Stage315, but the genuine
C/Python scene comparison correctly blocks on missing C files.

Stage317 closes this **packaging** gap while retaining original ROM
and graphics privacy. It does not simulate MAME gameplay or change the
Nintendo Switch NRO itself.

## Source-only GitHub artifact

`.github/workflows/cps1-private-native-scene-kit-317.yml` explicitly
packages only:

- Public Python source from `tools/*.py`, including Stages 299,
  305, 315, 316 and 317.
- The actual public Switch compositor source/headers:
  `cps1_scene.c/.h` and `cps1_tile.c/.h`.
- The publicly readable local-only shell runner from Stage316.

It compiles a public C shared library using native GCC and runs ROM-free
Stage305/315/317 regression tests using invented patterns. A public-Git
privacy gate runs before artifact publication. Binaries compiled during
CI are **not** uploaded; the ZIP contains only code.

The artifact never contains `dino.zip`, `gfx.bin`,
`sequence.bin`, input recordings, original graphics, X11 images,
user paths, original ROM digests, or Nintendo keys.

## User-owned private original ROM reproduction

Unpack the public code-only ZIP into a new private directory. Use a
separately held, canonical original `dino.zip` verified by the Stage299
historical MAME 0.106 16-member source CRC32/SHA1 manifest.

Stage315 must first have completed and placed its generated files
in an existing private staging directory:

```sh
python3 tools/cps1_private_original_gfx_synthetic_sd_315.py \
  --rom /private/roms/dino.zip \
  --out-dir /private/output/NEW-stage315-sd
```

Then run this **private native test** from the same extracted public
code checkout, with a working local GCC:

```sh
python3 tools/cps1_private_original_scene_preflight_317.py \
  --rom /private/roms/dino.zip \
  --sd-root /private/output/NEW-stage315-sd \
  --out /private/output/NEW-stage317-summary.json
```

This checks the entire original input's 16-member hashes, requires
the staged 4MiB gfx bytes to match that private ROM **exactly**, and
requires the Stage307 sequence to equal the canonical 14-frame
synthetic sequence. Then the code compiles the **actual portable
Switch C compositor** and compares with independent Python for 14
controlled artificial state scenarios; all 1,204,224 RGBA pixels must
match, with zero mismatches and all required palette/priority
differential outcomes.

The 0600 receipt is aggregate-only, containing no original ROM bytes,
private filenames/paths, content digests, original image data,
screenshots or emulator logs. If the archive or any private input is
missing, output is `BLOCKED_PRIVATE_ORIGINAL_GFX_NATIVE_C_PY_SCENE_PREFLIGHT`
and **no success may be claimed**.

A successful receipt would show:
`PRIVATE_ORIGINAL_GFX_NATIVE_C_PY_14_SCENES_AND_SD_MATCH`.

## Limits

This is a *static original graphics + synthetic runtime state* parity
test. It does **not** prove original arcade program execution,
real gameplay tilemap/palette/OBJ/VRAM, original frame capture, sound,
historical INP/WLF playback, real X11 display in NeXium, or physical
Nintendo Switch execution. Stage316's real private NeXium X11 opt-in
test remains a subsequent independent gate.

Retain Draft stacked on Stage316; do not merge into `main` without
explicit authorization.

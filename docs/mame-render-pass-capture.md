# dino MAME: synchronized render-pass CPS-1 frame capture (experimental)

This is the preferred experimental alternative to recording buffered OBJ
at a separate VBlank event. Our new capture hook executes **inside the
actual CPS-1 screen_update_cps1 renderer immediately AFTER render_layers**.
In one method invocation, it copies the framebuffer that the same
latched m_buffered_obj was used to draw, along with GFX RAM, CPS-A/B
registers and effective palette RGB.

It is a source-level research tool, NOT a redistributed MAME binary or
commercial game asset. No live MAME session has yet confirmed this hook.

## Preparing local MAME

From your private clone of MAME's source tree, generate a patch using the
exact original CPS-1 driver file:

```sh
python3 tools/mame_render_instrument.py \
  /path/to/mame/src/mame/capcom/cps1_v.cpp \
  --patch /tmp/dino-render-capture.patch
cd /path/to/mame
git apply --check /tmp/dino-render-capture.patch
git apply /tmp/dino-render-capture.patch
# Now rebuild MAME using its official development instructions.
```

Then (from a working directory with your privately held dino ROM set):

```sh
mkdir -p /private/cps1-render
export CPS1_RENDER_DUMP_DIR=/private/cps1-render
export CPS1_RENDER_DUMP_START=900
export CPS1_RENDER_DUMP_COUNT=6
/path/to/your/instrumented/mame dino -rompath /private/roms
```

The hook is restricted to game ID `dino`, a declared frame-number
window (1..120), and a **complete single cliprect** covering the native
CPS-1 viewport (X 64..447, Y 16..239). If MAME performs partial
screen updates and never invokes this hook with the whole viewport in
one cliprect, this collector deliberately captures **nothing**.
It does not silently stitch together potentially inconsistent moments.

## File set per captured render

For frame number 900:

| Filename suffix | Bytes | Source |
|---|---:|---|
| `gfxram-be.bin` | 196608 | 192 KiB mapped QSound graphics RAM |
| `cps-a-be.bin` | 64 | CPS-A register words |
| `cps-b-be.bin` | 64 | CPS-B register words |
| `buffered-obj-be.bin` | 2048 | VBlank-latched m_buffered_obj used by renderer |
| `palette-rgb24.bin` | 9216 | 3072 effective palette RGB entries |
| `reference-rgb24.bin` | 258048 | Cropped 384x224 real RGB image, copied from indexed bitmap |
| `manifest.json` | varies | Capture phase, dimensions, provenance, status |

Every sample uses big-endian words for RAM/register/OBJ; RGB channels
are ordinary [R,G,B] bytes. All seven files share the common
`frame-00000900.` filename prefix. The manifest is written last.
The import step validates the size of every binary file.

## Convert to a private frame snapshot and reference PNG

```sh
python3 tools/mame_render_import.py /private/cps1-render frame-00000900 \
  --out-dir /private/cps1-parity
```

Outputs `frame-00000900.snapshot.json` and
`frame-00000900.reference.png`. The JSON has the actual buffered OBJ
and effective palette; it is thus **eligible for attempting**
a reconstruction comparison, but explicitly states
`pixel_parity_verified: false`.

Use your original ROM privately to render the same snapshot and measure
differences:

```sh
python3 tools/cps1_frame.py /private/dino.zip \
  /private/cps1-parity/frame-00000900.snapshot.json \
  --out /private/cps1-parity/recreated.png
python3 tools/frame_compare.py \
  /private/cps1-parity/frame-00000900.reference.png \
  /private/cps1-parity/recreated.png \
  --diff /private/cps1-parity/error.png
```

No comparison is expected to be pixel-exact yet: the renderer lacks
some MAME effects, and we have NOT captured a real frame in this
environment. The comparison result, not the presence of this tool,
is the only basis for a future pixel-parity claim.

## Verification and limitations

- Unit tests compile/execute the C++ insertion in a synthetic MAME driver
  stub, check real output byte lengths/endianness, and reject partial
  cliprects. Further tests reject unverified parity claims and invalid
  mapped GFX RAM addresses.
- The source insertion is pinned to the MAME cps1_v.cpp
  `screen_update_cps1` and `render_layers` signatures. A driver
  revision that changes them must be reviewed before applying.
- The collector uses standard file I/O; files and directories must
  be writable and available locally. Incomplete files are rejected.
- Real-time writing during game rendering can cause frame-time stalls.
  The tool is deliberately opt-in and limited to a short frame window.
- Other CPS-1 driver/game variants, flipscreen edge cases, partial
  raster updates, hardware initialization and emulator timing are
  outside this diagnostic's guarantee.
- No Switch NRO is modified at this stage.

Authoritative implementation:
https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp

Do not upload real captured RAM, original ROMs, images, palettes or
extracted copyrighted graphics to GitHub.

## One-command local pixel-parity measurement

New `tools/mame_frame_parity.py` connects all previously independent
tools into an end-to-end, **local-only** comparison. It requires seven
validated same-render-pass capture files and a privately owned dino ROM.
It never attempts to match an incomplete Lua/VBlank-only capture.

```sh
python3 tools/mame_frame_parity.py \
  /private/dino.zip /private/cps1-render frame-00000900 \
  --out-dir /private/cps1-parity \
  --require-exact
```

Outputs four files:

- `frame-00000900.mame-reference.png`: unscaled 384x224 MAME reference;
- `frame-00000900.reconstructed.png`: this project's partial CPS-1
  renderer, fed exactly the captured RAM, buffer and palette;
- `frame-00000900.error-heatmap.png`: red-channel per-pixel maximum
  absolute RGB/RGBA channel difference;
- `frame-00000900.parity-report.json`: frame dimensions, mismatch count
  and ratio, mean absolute channel error, maximum channel error, first
  mismatch position, PNG SHA256 checksums and strict provenance flags.

With `--require-exact`, exit code 0 means **one captured frame** matched,
1 means mismatches were measured, and 2 means input validation or I/O
failed. Without that flag, it records nonzero mismatch metrics normally.

Reports always mark `game_wide_parity_verified: false` and
`native_switch_runtime_tested: false`. The comparator refuses incomplete
OBJ, wrong capture manifest, invalid GFX sizes and attempts to use
previously 'verified' incoming snapshots.

Five ROM-free synthetic regression tests verify a full 86,016-pixel
exact match, a deliberate single-pixel difference and heatmap location,
and rejection of incomplete or invalid inputs. These exercises test
**the measurement pipeline**; they are NOT evidence that any real
Cadillacs and Dinosaurs game frame has reached pixel parity.

## New safeguards for complete, immutable captures

The experimental renderer can be called repeatedly for the **same MAME
frame number**, including raster/partial screen refresh events. Previously
a repeated render could overwrite already saved binary data. The capture
hook now uses `frame-XXXXXXXX.manifest.json` as a completion marker.
Once present, the hook **does not write that frame again**, even if the
emulator is restarted and the same frame number occurs.

Before writing the marker it reopens **all six binary streams** and
confirms their exact contract sizes: 196608, 64, 64, 2048, 9216 and
258048 bytes. A missing, truncated or inaccessible stream prevents the
manifest. The Python importer requires the manifest and independently
validates all six streams.

This is a **fail-closed completion gate**, not an atomic transaction across
the whole operating system. If a write fails, partial uncommitted binary
files can remain in the private capture directory. Remove those incomplete
files before retrying. Do not copy a partially written set into a
different directory or mix files between runs.

Additional compiled C++ regression checks deliberately change GFX RAM and
buffered OBJ between two callbacks for the same frame and verify the first
snapshot is preserved. Another check blocks a required output path and
confirms **no manifest is committed**.

Manifest filenames are built using `std::string`, avoiding truncation
warnings under GCC `-Werror` for long output paths. This check has
been run on the synthetic C++ stand-in, not a complete MAME build.

## Write-success gate (hardened)

A further fail-closed correction ensures that a pre-existing incomplete
binary **cannot accidentally satisfy the size check** if writing the new
content fails. The capture now records the result of *every* binary
`fwrite` and `fclose` operation, including all 86,016 rendered RGB
pixels and 3,072 palette entries. The completed manifest is written
only if **every fresh write succeeded** and all file sizes are exact.

An opt-in C++17 regression test compiles the generated hook with
`-Wall -Wextra -Werror`, simulates two different render calls for
the same frame and a blocked output path, and ensures that no
incorrect manifest is committed. The native source has not yet been
built with the full upstream MAME toolchain.

## Spatial error analysis (new)

To make parity failures actionable, `tools/mame_frame_parity.py` now adds a
`spatial_error_profile` section to the same JSON report. No extra game
assets or images are needed.

For the actual 384x224 CPS-1 viewport it records:

- Inclusive mismatch bounds `[min_x, min_y, max_x, max_y]`, or `null`
  if RGB values are identical.
- Error counts for each of the 224 scanlines and each of the 384 columns.
- Number of affected rows and columns, plus the busiest single scanline.
- Per-channel R/G/B mismatch counts and total absolute channel errors.
- Mismatch counts in all four screen quadrants.

These metrics help distinguish global tilemap/scroll misalignment from
localized sprite issues or a palette-component mismatch. All coordinates
refer to the **cropped 384x224 reference frame** (not the original hardware
512x256 coordinate space). Alpha is excluded from this second RGB-only
profile, while the existing exact RGBA comparator remains authoritative
for the single-frame `identical` boolean.

Five ROM-free standalone regressions cover perfect RGB, a single pixel,
four quadrants, individual channels, alpha-only changes and malformed
dimensions. Existing end-to-end parity tests also assert the new spatial
section for synthetic equal and one-pixel-different frames.

Neither the spatial report nor a matching synthetic fixture proves real
MAME parity or playable game logic.

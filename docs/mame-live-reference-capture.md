# Experimental real MAME reference-frame capture — dino World 930201

This is the first local-only bridge from a **running, user-owned MAME game**
to reference-frame analysis. The Lua script is written against the publicly
documented MAME 0.289 API and was **executed under Lua 5.4 with synthetic
MAME API stubs**, confirming file sizes, endian layout and manifest format.
It has **not yet been executed against running MAME** in our CI environment.
The Python importer is unit-tested with synthetic data.

## Exact QSound video memory and palette inputs

The dino World 930201 QSound main-CPU [MAME memory map](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1.cpp) has CPS-A and CPS-B shared registers at `0x800100` and `0x800140`; graphics RAM at **0x900000–0x92ffff (0x30000 bytes / 192 KiB)**. The older generic tool's 0x40000-byte aperture must not be mistaken for 0x40000 bytes of physically mapped RAM.

The new `tools/mame_cps1_capture.lua` asks MAME for:

| File per frame | Exact bytes | Meaning |
|---|---:|---|
| `frame-XXXXXXXX.gfxram-be.bin` | 196,608 | 68000-visible graphics RAM, 16-bit big-endian |
| `frame-XXXXXXXX.cps-a-be.bin` | 64 | CPS-A shared hardware registers |
| `frame-XXXXXXXX.cps-b-be.bin` | 64 | CPS-B shared hardware registers |
| `frame-XXXXXXXX.palette-rgb24.bin` | 9,216 | **Effective MAME 3072-color RGB palette** |
| `frame-XXXXXXXX.reference-rgb24.bin` | 258,048 | Native 384×224 MAME RGB framebuffer |
| `frame-XXXXXXXX.manifest.json` | variable | Frame number, provenance and known omissions |

The Lua script dynamically calibrates memory-share word addressing against
the 68000 address space. It refuses ambiguous calibration rather than
silently producing corrupted memory. It captures after the MAME display
update and records the actual effective palette, rather than attempting to
derive frame colors solely from static ROM or mutable source palette RAM.

**Key limitation:** The internal **VBlank-latched OBJ buffer** used to
render the original sprites is not accessible through these ordinary Lua
memory shares. Capturing current gfx RAM is *not equivalent* to capturing
buffered OBJ, and may occur at another moment than the image on screen.
The manifest explicitly records `"obj_latch":"NOT_CAPTURED"` and
`"pixel_parity_eligible":false`.

## How to run using your personal original game files

Install a recent official MAME and arrange your privately held dino ROM set
in the emulator's ROM directory. Create the output directory *before*
launching MAME:

```sh
mkdir -p cps1-captures
mame dino -rompath /private/mame-roms \
  -autoboot_script /path/to/project/tools/mame_cps1_capture.lua
```

By default the Lua script begins at frame 900, takes 6 captures 2 frames
apart. Adjust `START_FRAME`, `FRAME_COUNT`, `FRAME_STEP` at the top of
the script to choose an actual gameplay interval. The Lua script can report
calibration errors on uniform/black game screens; retry during gameplay.

Import a captured frame:

```sh
python3 tools/mame_capture_import.py cps1-captures frame-00000900 \
  --out-dir local_outputs/real-reference
```

Produces a **384×224 reference PNG containing real MAME pixels** and a
`*.partial-snapshot.json` with effective palette/scrolls/VRAM and an
explicit missing-sprite indicator. It does not insert fake sprites.

The importer checks lengths and big-endian word order and **rejects scroll
register bases outside actual 0x30000-byte mapped graphics RAM**, despite
using padded 0x40000 buffer solely for backward compatibility. It also
refuses to overwrite existing local results.

The `tools/cps1_scene_export.py` native `scene.bin` exporter now rejects
partial snapshots with `pixel_parity_eligible:false` / unavailable
buffered OBJ. A real MAME screenshot alone does not establish parity of
the Switch compositor.

## What is still needed

1. Execute and calibrate the Lua script on a supported MAME installation.
2. Capture a time-consistent, original **latched** OBJ buffer via a verified
   extension/instrumentation of MAME, not a guessed array.
3. Verify real background/register timing and exact pixel parity using
   `tools/frame_compare.py`.
4. Only then export authentic complete `scene.bin` or sequences for Switch.

## Sources

- [MAME CPS-1 QSound map](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1.cpp)
- [MAME scripting and autoboot_script](https://docs.mamedev.org/luascript/index.html)
- [MAME shared-memory Lua API](https://docs.mamedev.org/luascript/ref-mem.html)
- [MAME palette, pixel read and screen API](https://docs.mamedev.org/luascript/ref-devices.html)

All actual ROMs, captured game graphics, palettes, screenshots and RAM
dumps must remain outside GitHub. Tests use synthetic bytes only.

### Lua smoke test

`tests/test_mame_lua_stub.py` optionally loads the actual capture script
under an installed Lua 5.4 shared library, with an artificial in-memory
simulation of MAME's named shares, palette, screen and frame-complete hook.
It checks that six expected files are written and that byte lengths,
big-endian words, manifest and honesty/provenance fields are correct.
If liblua5.4 is not available, the smoke test is skipped and reported as
such. **This is not a real MAME capture.**


## Stage 39 — frame identity checks and non-overwriting captures

A real MAME reference can only be useful for later pixel-parity analysis
if its name, frame number, geometry and capture method are internally
consistent. `tools/mame_capture_manifest.py` now validates captures
**before reading their binary frame data**:

- Require a canonical `frame-XXXXXXXX` filename stem with exactly eight
  ASCII digits. Reject absolute paths and traversal in the frame argument.
- Require `manifest.frame` to match that filename exactly (not a boolean
  or a coerced string), with `capture_hook: frame_done`.
- Check dino/QSound declared graphics RAM and CPS-A/B register sizes,
  384×224 RGB frame dimensions, palette bytes, endianness, and unavailable
  VBlank-latched OBJ provenance. Absent/wrong declarations fail closed.
- A partial Lua snapshot **remains ineligible for real-frame renderer
  parity** regardless of matching metadata. It does not become an
  authentic buffered-OBJ snapshot.

The Lua script now checks **all six destination filenames** before
writing the first output. It refuses to overwrite any existing frame
component, including a frame captured during a previous MAME session.
To recapture the same frame index, create a **fresh private output
directory** (and update `OUTPUT_DIR` in the script), or move/archive the
old capture yourself. The script is not a multi-process atomic file lock;
run only one capture process per output directory.

### Verification boundary

The *exact* new Python manifest helper and its eight ROM-free unittest
methods were run locally: **8/8 passed**; Git blob hashes were compared
against the committed GitHub file blobs. The **exact committed Lua
capture-script blob** was also run locally under Lua 5.4 with a
synthetic API stub: **2/2 local integration checks passed**, confirming
six output sizes and refusal to overwrite existing data. Neither test
loads commercial assets or represents a real MAME session.

Updated Python importer tests and the repository's optional Lua
smoke-test suite have been committed but are **not independently
verified as a complete GitHub checkout**: GitHub Actions runners fail
before any job steps (issue #20). They must run before merging.

This does **not** cryptographically bind binary content to the manifest.
Mixing same-size binaries between capture sets cannot be detected by
these metadata checks alone; checksums and synchronized VBlank-latched
sprite memory are future capture-integrity milestones.

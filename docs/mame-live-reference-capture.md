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

## Pixel-format correctness — verified against MAME core C++

MAME's Lua documentation describes two *underlying* screen formats:
palette-indexed and direct RGB. However, the authoritative implementation
of `screen_device::pixels(u32 *)` in MAME
[`src/emu/screen.cpp`](https://github.com/mamedev/mame/blob/master/src/emu/screen.cpp)
**resolves indexed pixels through the current effective palette before
returning the buffer**. For direct RGB bitmaps, it returns the RGB value.

Consequently, the output of `screen:pixels()` is packed **RGB32 in both
cases**. Previous double palette lookup was a serious bug: it could reject
valid pixels or corrupt colors, especially for RGB values exceeding the
number of palette entries.

The capture now uses the documented bulk `screen:pixels()` method and
Lua `string.unpack('=I4')` (host byte order) and ALWAYS extracts
RGB channels directly. It records:

- `reference_pixel_encoding: "rgb32_resolved"` — the **output** format
  after MAME's screen conversion;
- `reference_source_format: "indexed_bitmap" | "rgb_bitmap"` — the
  **underlying** screen format, inferred from `screen.palette`.

The Python importer requires both fields and checks the exact 384×224
visible-area dimensions and frame stem. Lua 5.4 synthetic smoke tests
exercise both native framebuffer types and ensure effective RGB values
are not converted through the palette twice. Still not a confirmed
runtime capture from real MAME.

Source references:
- [MAME screen.cpp native pixel and pixels conversion](https://github.com/mamedev/mame/blob/master/src/emu/screen.cpp)
- [MAME Lua screen device API](https://docs.mamedev.org/luascript/ref-devices.html)
- [MAME Lua memory shares](https://docs.mamedev.org/luascript/ref-mem.html)

## Repeatable audit of multiple captured frames

Added `tools/mame_capture_audit.py`, a **ROM-free local audit** for actual
MAME reference dumps. It accepts at most 120 `frame-XXXXXXXX` records.

```sh
python3 tools/mame_capture_audit.py cps1-captures \
  --output local_outputs/mame-capture-audit.json
```

Each capture is checked against the full six-file contract: lengths,
`dino` ID/frame number, MAME effective palette provenance, original
384×224 dimensions, big-endian RAM, **RGB32-resolved screen pixels**
and the explicit absence of the VBlank-latched OBJ buffer. The report
contains SHA-256 hashes of each binary and the number of distinct RGB
colors; it flags all-uniform frames, which may signify loading/blank video.
For consecutive frames it computes exact changed-pixel counts, changed
palette entries, changed RAM/register flags and frame-number gaps.

No claim of actual MAME execution or pixel-exact re-rendering is made
by these diagnostics. A frame can change while sprites remain inaccessible,
and even a fully verified dump is not equivalent to full arcade gameplay.
The auditor intentionally refuses manifests that falsely claim a complete
sprite buffer or one-frame pixel parity. Nine new deterministic synthetic
tests exercise this contract, temporal deltas, malformed stems and safe
file creation. Raw captures, generated reports and original art remain local.

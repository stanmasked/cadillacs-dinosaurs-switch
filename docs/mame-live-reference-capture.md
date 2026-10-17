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
It checks six complete frame bundles (36 files), CRC32, big-endian words,
manifest provenance and strict multi-frame analyzer compatibility.
If liblua5.4 is not available, the smoke test is skipped and reported as
such. **This is not a real MAME capture.**


### Stage 64: checksum-complete private Lua captures

The original Lua script emitted the five binary files and a manifest
**without** `file_crc32`, while the multi-frame verifier introduced
in Stage 40/52 requires the **complete five-file checksum map**.
Consequently the recorder's own output was incompatible with the
strict sequence analyser. This mismatch has now been corrected in
the shipped `tools/mame_cps1_capture.lua`.

For each nominal frame the Lua recorder now serializes exactly the
same five existing captures, calculates canonical CRC32 on the
**exact bytes being written**, and writes the manifest **last**
with the five lowercase eight-digit hexadecimal CRC32 values.
CRC32 catches accidental damage and mixing; it does not
authenticate original MAME frames or render callback timing.

Before serializing any frame it checks whether any of the six
output paths already exists and refuses to overwrite a prior
private capture. This protects against inadvertent repeated
recording into the same directory. It cannot ensure an atomic
multi-file write if the emulator crashes mid-capture: incomplete
datasets remain invalid and must be recaptured privately.

The Lua 5.4 synthetic fixture now emits **six nominal frames**
(900, 902, 904, 906, 908, 910). CI independently calculates
Python zlib CRC32 on all 30 binary files, feeds the Lua-generated
manifests plus **synthetic** C++ records to the real
`mame_obj_sequence_alignment.py` CLI with V2 latch-count
validation, and verifies every sync/parity eligibility flag
remains false. A separate Lua test confirms an existing manifest
is never overwritten. No original game ROM is used in these
tests.

For an **actual private test**, use the confirmed built
instrumented MAME 0.289 from the Stage 60/62 process with a
legitimately owned `dino` ROM set available only in a private
local ROM directory. Before running, create an **empty**
`cps1-captures` directory in the process working directory,
then launch the emulator with the project's Lua
`-autoboot_script` path, as described above. The C++ video probe
and Lua collector must be used with the **same process and
working directory**. Do not upload any source-ROM set, frame
RGB, RAM, OBJ, screenshots or a full capture bundle to GitHub.

After exactly six captures, the private multiframe CLI can
validate the bundle with `--latch-count-evidence`. Real frame
alignment is only a hypothesis until original runtime timing
is independently established; captured buffers must **not**
be promoted to Switch-authentic scene assets yet.


## Stage 65 — private full-MAME gameplay capture session

The real MAME 0.289 dino subset **compiled and linked** with the
experimentally instrumented CPS-1 video code; the strict ROM-free
driver/XML and ELF V2 identity gates also passed GitHub Actions.
The emulator executable is **not distributed** and original
arcade ROMs must be legally held and kept entirely local.

New local-only script: tools/mame_private_dino_session.py

From a checkout of this repository, with the privately built
instrumented MAME executable and its source tree present, run:

    mkdir -p -m 700 /private/local-dino-session
    python3 tools/mame_private_dino_session.py --mame /private/mame0289/dino --mame-tree /private/mame0289 --rom-dir /private/owned-mame-roms --workspace /private/local-dino-session --preflight-only

Use your own actual paths. Preflight checks filesystem
isolation/permissions only; it does not launch the game or
read any ROM bytes. Then remove --preflight-only and run the
same command to start local MAME after ROM-free ELF/driver
verification. The runtime invokes the shipped Lua capture
through the -autoboot_script option and keeps ROM paths, logs
and original captures outside the repository.

The instrumented MAME and Lua collector currently target exactly
six nominal frames: 900, 902, 904, 906, 908 and 910. They are
hardcoded in **both** the generated C++ and Lua probe. Launch
the game privately, reach active gameplay by the capture range,
and exit MAME normally after the six frames are saved. The
local timeout defaults to 1800 seconds.

The session creates an empty private cps1-captures subdirectory
(mode 0700), and a mode-0600 private MAME log. After MAME exits
successfully, the real multiframe analyzer validates all 30
Lua binaries against five complete per-frame CRC32 manifests,
all C++ register and 2048-byte buffered OBJ sidecars, and six
strict V2 latch-count fingerprints. Its diagnostic-only JSON
is stored privately, with mode 0600.

A workspace must already exist, be mode 0700 on POSIX and be
completely separate from the repo, ROM directory and MAME
source tree. The launcher refuses existing log/capture/report
paths and symlinked MAME executables. A timeout, failed MAME,
absent frame, invalid CRC, legacy V1 sidecar or mismatched
OBJ fingerprint refuses success; partial private files are
kept for local inspection, never published. Start a new session
in a **new empty private workspace** rather than overwriting
old captures.

Success is reported only as PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY.
It does **not** prove real game frame/VBlank synchronization,
that the captured original game was actively playing, pixel
parity, original-game authenticity, or native Switch gameplay.

The new regression tests exercise synthetic fake game execution
and all local privacy/integrity failure paths. Actual original
dino ROM gameplay has still **not** been executed and confirmed
as part of this development stage. Never upload original ROMs,
private game graphics, or raw capture files to GitHub.


## Stage 66 — reference RGB activity, not gameplay certification

An internally consistent six-frame capture is not automatically
informative for reverse engineering: a black screen, title screen,
static pause menu, or uniformly colored test image can have valid
manifest checksums and perfectly matched V2 OBJ fingerprints.

The private session now runs
`tools/mame_reference_activity.py` **only after** its strict
multiframe CRC32 and OBJ V2 validation. It examines six bounded
384×224 RGB24 reference files, counting:

- exact RGB color diversity and nonblack pixels in each frame;
- exact changed RGB pixels between each adjacent nominal frame;
- static or all-black reference sequences, and whether every
  frame contains just one RGB color.

These are **byte-level observations**, not gameplay detection.
The status may be `ALL_BLACK_REFERENCE_SEQUENCE`,
`STATIC_REFERENCE_SEQUENCE`, or
`REFERENCE_BYTES_CHANGED_UNVERIFIED`. A solid screen that
changes color still indicates only changed bytes, not genuine
playable game footage; a static screen may be a valid frame.

The local JSON printed at the end of the private session contains
`reference_activity` with aggregate counts only. No raw image,
sprite words, user ROM path or screenshots are published or
added to the project. `active_gameplay_verified:false`,
`frame_sync_verified:false` and `pixel_parity_eligible:false`
are preserved independently of how much activity is observed.

The launcher also refuses private ROM directories and full
upstream source trees placed **inside the public project checkout**,
to reduce the risk of a future accidental `git add` publishing
someone's original commercial game files or complete MAME copy.

Ten new ROM-free Python regressions cover all-black, static,
color-changing-but-uninformative, one-pixel and two-color
synthetic images, missing/truncated/oversized files, sample
bounds, metadata privacy and the end-to-end local mock session.
No true `dino` game frames were recorded during this stage.


## Stage 67 — cross-stream observations, no synchronization certification

The private session already checks all five per-frame Lua CRC32 inputs,
C++ OBJ/register probe completeness, V2 latch-count fingerprints and
reference RGB activity. The missing link for *selecting a useful
follow-up investigation* was a per-interval comparison of these
different observations at the same **nominal** frame labels.

New local-only module:
`tools/mame_multistream_interval_evidence.py`.

After all existing CRC32, V2 FNV, size and RGB checks succeed, the
private-session launcher now produces a
`multistream_interval_evidence` metadata object. For each of the
five successive intervals (900→902, 902→904, 904→906, 906→908,
908→910), the object describes:

- Changed native reference RGB pixels (not actual RGB content).
- Changed raw eight-byte buffered CPS-1 OBJ slots, **not sprite count**.
- Changed 16-bit CPS-1 register words in the C++ video-update probe.
- Number of observed emulator `cps1_objram_latch` callback-count
  increments between two selected samples.
- Co-occurrence and divergent observations such as OBJ changes
  without callback count increments, or callbacks without OBJ changes.

All inputs must have identical six-label sequences, valid step
bounds, strict numeric ranges, unchanged source totals, explicit
unverified synchronization/parity flags and **complete V2 FNV
binding for every sample**. Missing or conflicting reports fail
closed instead of issuing a plausible-looking conclusion.

The status is either
`LOW_INFORMATION_FOR_MULTISTREAM_STUDY` or
`MULTISTREAM_VARIATION_OBSERVED_UNVERIFIED`.
This is a **data-triage label**, not a synchronization verdict.
Even if RGB, OBJ and latch counts all change at the same nominal
frame labels, they still come from one instrumented emulator
process; that correlation cannot independently establish original
hardware VBlank timing or the correct displayed frame.

The module emits only interval counts and safe boolean observations,
no raw commercial RGB/OBJ game bytes, original image, ROM data,
user paths or captured sprite-word hashes. It always sets
`hardware_vblank_observed:false`,
`active_gameplay_verified:false`,
`obj_latch_age_verified:false`,
`frame_sync_verified:false` and
`pixel_parity_eligible:false`.

Thirteen direct ROM-free tests plus the end-to-end session
integration assertion verify co-change intervals, divergent
callbacks, static/black frames, version and label mismatches,
forged totals, invalid numeric data and original-source privacy.
These tests are synthetic and **do not run `dino` ROM gameplay**.
A truly independent timing reference or actual trusted game
frame capture is still required before making frame-parity claims.

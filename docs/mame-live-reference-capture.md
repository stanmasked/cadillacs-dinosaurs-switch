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


## Stage 68 — all-or-nothing publication of the private audit report

The local private MAME session previously handed the **final**
`dino-latch-diagnostic.json` path directly to the multiframe
analyzer. The analyzer wrote JSON as soon as its own checks
finished, but **later** session-level V2, reference RGB activity
and cross-stream checks could still reject the capture. This
could leave a final-looking report on disk even though the full
session audit had failed.

The corrected local workflow stages the analyzer's JSON in a
**private temporary directory within the 0700 workspace**. It
then verifies the bounded JSON, complete six-sample V2 OBJ
fingerprints and conservative synchronization flags, computes
the RGB activity and the nominal RGB/OBJ/register/latch interval
comparison, and only then writes a **completed** JSON record.
The completed report also includes:

- the original unmodified per-frame register/OBJ/latch diagnostic
  data, with its original conservative verification fields;
- `reference_activity` and `multistream_interval_evidence`;
- `private_capture_completion` with
  `full_check_sequence_completed:true` and explicit false
  authenticity, gameplay, VBlank, frame sync and parity claims.

The completed JSON is written, flushed, fsynced and set to
mode 0600 before **exclusive, atomic hard-link publication**
under `dino-latch-diagnostic.json`. A final report created
concurrently by another process is never overwritten, and
the temporary directory is automatically cleaned up.
If the CLI fails, JSON is malformed or oversized, V2 is
legacy/incomplete, activity analysis fails, or interval
metadata is inconsistent, **no final report is published**.
The private raw capture and MAME log remain untouched for
local investigation. Use a new empty 0700 workspace for
another attempt.

This publication guarantee applies to the **diagnostic JSON
only**. The original multi-file Lua/C++ capture is still not
crash-atomic; incomplete frames will fail normal CRC/FNV
validation. A published local report certifies at most
`PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY`, not original
game authenticity, physical VBlank age, active gameplay
or Nintendo Switch pixel parity.

Five added ROM-free regression methods cover a late RGB
failure, a late cross-stream failure, malformed or partial
analyzer output, a final filename collision after the
emulator has run, and temporary-directory cleanup, while
the prior end-to-end session test checks that all required
sections appear only on a complete synthetic pass.


## Stage 69 — private capture source stability across the audit

The Stage 68 publication gate already protects the **final** JSON
from being created before all checks complete. Yet a local raw
capture could be edited, replaced or supplemented during the
multi-step CRC/FNV/RGB inspection, leaving a completed JSON
based on **outdated** source observations.

Stage 69 adds `tools/mame_private_capture_stability.py`. Immediately
after successful local MAME process exit and **before** any audit
analysis, the private launcher requires exactly **54 regular files**:
6 nominal frame labels (900, 902, 904, 906, 908, 910) and 9 inputs
per frame (5 Lua binaries, 1 CRC32 manifest, 2 C++ binary probes,
1 V2 latch-count sidecar). Missing or unexpected files, directories,
symlinks and hardlinked files are rejected. File sizes are fixed or
strictly bounded per the established capture schema.

The checker hashes each source file with streamed SHA-256, retains
its inode, device, byte length and nanosecond modification/change
times **only in process memory**, and requires exact equality after
the cross-stream audit. It scans again after the completed JSON is
formatted and fsynced, **immediately before exclusive publication**
under the final report name. Any file addition, deletion, inode
replacement, same-length change or changed checksum rejects the
session without publishing a final report. The staged temporary
report is cleaned up. The original private files are never
overwritten or uploaded.

A successful final JSON includes only
`private_capture_source_stability` metadata with
`source_files_checked:54` and
`source_files_unchanged_during_audit:true`, explicitly describing
local SHA-256 source comparison **without disclosing the hashes**.
This supplements, rather than replaces, Lua CRC32 and the C++
OBJ/V2 FNV-1a binding.

The check is a **best-effort consistency snapshot, not a filesystem
lock, cryptographic proof of authentic ROM content or an independent
frame-time reference**. Files could still be changed after report
publication; matching bytes do not prove genuine playable game
frames, hardware VBlank latch timing, active gameplay or Switch
pixel parity. The tool is intended for private, nonadversarial
single-user captures.

Ten direct ROM-free regression methods cover complete 54-file
snapshots, same-size mutations, manifest edits, added/missing
files, symlink/hardlink and inode replacement rejection, size
bounds, invalid frame intervals and metadata confidentiality.
Three additional end-to-end synthetic session tests insert input
mutations during cross-stream analysis, after JSON serialization,
or add unexpected capture files. They verify **no final JSON**
is published on any such failure. No actual commercial dino ROM
was used or uploaded during this stage.


## Stage 70 — same-launcher session labels across Lua and C++

Even a fully CRC32-verified, SHA-256-stable 54-file set can
contain **accidentally combined captures from separate MAME
processes**. Such data may have valid frame numbers and sizes
without sharing the same run.

The private launcher now generates a **fresh random 128-bit
lowercase hexadecimal session label** at runtime, passes it
only in the local `CPS1_DINO_CAPTURE_SESSION` process environment,
and keeps the label out of the completed diagnostic JSON.

Two separate MAME capture hooks observe that label:

- Lua writes `capture_session` into each original six-frame
  CRC32 manifest. Standalone Lua tests without a launcher
  explicitly write `UNBOUND`, which the private launcher rejects.
- The generated MAME 0.289 C++ video hook still emits its
  backwards-compatible `CPS1_DINO_LATCH_V2` header and buffered
  OBJ FNV-1a 64 fingerprint. When a canonical label exists in
  the process environment, the **same existing V2 text file**
  gains a second line, `CPS1_DINO_SESSION <32-hex-label>`.
  It does not create an extra captured file.

The optional generic latch reader can consume both unstamped
historical V2 records and stamped V2 records. It rejects mixed
session labels or a series containing both stamped and unstamped
records. The new strict local-only
`tools/mame_capture_session_binding.py` checks the label in
**all six Lua manifests and all six corresponding C++ sidecars**
against the launcher's **original expected label**. The
private session never publishes a completed report if any
label is missing, malformed or different. The final JSON
contains only safe `capture_session_binding` counts and
`shared_session_label_consistent:true`, not the raw label.

This is a **local run-consistency tag**, not cryptographic
authentication. Both labels are produced in the *same emulator
process* from one inherited environment and are not independent
trusted observations. A modified emulator could forge them;
they do not prove that the original game was playing, which
hardware VBlank buffered OBJ, or which pixels were displayed.
All real-game authenticity, active-gameplay, frame-sync and
pixel-parity flags remain false.

The new source generator modifies the real upstream C++ injection
by reading `std::getenv` from the existing C++ video probe.
Its original source must still pass the byte-for-byte
unmodified MAME 0.289 patch/reconstruction gate; the generated
C++ is additionally compiled and **executed in the ROM-free
mock MAME harness with the session environment enabled**.
This verifies the injected C++ source behavior but does not
replace compilation or runtime testing of the updated code
inside a fresh full upstream MAME build.

No commercial ROM, captured RGB, OBJ or original sprite data
is added to the public repository. For complete private
session integrity, the label check is followed by the Stage
69 file-stability check and Stage 68 exclusive final JSON
publication; use a new empty private workspace per run.


## Stage 71 — full-tree MAME 0.289 with session-aware C++

GitHub Actions run
[39047853025](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39047853025)
successfully built the **genuine pinned MAME 0.289 `dino` subtarget**
from the upstream source tree with the current generated C++ patch.
It passed source reconstruction, ROM-free `-listxml dino` and compiled
`cps1_v.o` marker verification for `CPS1_DINO_LATCH_V2`,
`CPS1_DINO_SESSION` and `CPS1_DINO_CAPTURE_SESSION`.
Current-head Python CI passed 404/404 tests and the devkitPro Nintendo
Switch NRO build passed. This is a **successful compilation**, not a
real MAME original-game launch or a measured VBlank correlation.

## Stage 72 — prove probe markers also survived final ELF linking

A freshly compiled and session-marked `cps1_v.o` does not by itself
prove the `dino` executable used for the next capture was actually
linked against that object: a stale or replaced executable might still
pass driver XML plus build-tree object inspection.

The ROM-free verifier therefore scans the **actual linked executable**
for all three expected C++ strings. It first checks the ELF signature,
bounds the file size, and streams the bytes in bounded chunks with
cross-chunk overlap instead of loading the potentially large executable
into memory. A V2-only executable, missing session sidecar code marker,
missing session environment marker, truncated/non-ELF executable or
symlink fails without launching any original game ROM.

The private local capture launcher now also explicitly requires the
session-aware compiled object and linked executable booleans before
creating its capture directory, log or final report. ROM-free
regressions cover marker boundaries, false positives from an updated
object paired with an old linked executable, and fail-closed launcher
preflight. Neither a linked string nor the shared process environment
is an independent authentication of MAME execution, physical VBlank,
arcade-game identity, or pixel parity: all of those claims stay false.
No executable, ROM or captured game bytes are published.


## Stage 73 — ROM-free verification before first private gameplay

The previous `--preflight-only` mode checked only filesystem isolation.
It did **not** compile, run or verify the executable: its positive result
must never be interpreted as proof a recent instrumented emulator is ready.

A second, explicit private launcher mode checks the actual built executable
**without executing the original `dino` game or accessing ROM contents**:

```sh
python3 tools/mame_private_dino_session.py \\
  --mame /private/mame0289/dino \\
  --mame-tree /private/mame0289 \\
  --rom-dir /private/owned-mame-roms \\
  --workspace /private/local-dino-session \\
  --verify-build-only
```

Like the existing filesystem preflight, this mode requires a pre-existing
empty, isolated mode-0700 workspace. Unlike it, the verifier executes
**ROM-free `-listxml dino` only**, checks the genuine MAME 0.289 driver,
the compiled session-aware CPS-1 object and the three markers in the
**final linked ELF**. No game process is launched, no capture files or
report/log directories are created, and no original ROM bytes are read.
The returned status is `ROM_FREE_SESSION_AWARE_MAME_BUILD_VERIFIED`
with explicit `game_executed:false` and
`linked_probe_runtime_verified:false`. Private paths and the raw
session label are never included in the returned JSON.

Use `--verify-build-only` **or** `--preflight-only`, never both.
When both filesystem and binary verification are successful, a separate
normal invocation (without either flag) can run a privately owned ROM
set in the local MAME executable. A synthetically tested build gate does
not prove game activity, original VBlank timing or pixel parity.


## Stage 74 — inspect a private MAME build before obtaining game files

The ROM-free `--verify-build-only` mode no longer requires a ROM directory
or a capture workspace. It now accepts **only the local executable and its
source/build tree**:

```sh
python3 tools/mame_private_dino_session.py \\
  --mame /private/mame0289/dino \\
  --mame-tree /private/mame0289 \\
  --verify-build-only
```

This verifies that the executable is present, executable and not a symlink,
that the full upstream source tree is **outside the public checkout**, then
runs `-listxml dino`, checks the compiled CPS-1 object and inspects the
actual linked ELF for the three session-aware probe strings. No original
commercial game data, ROM path, output workspace or local gameplay is
needed. The command produces only a path-free ROM-free verification result.

The earlier four-path `--verify-build-only` form remains accepted for
compatibility and still validates its supplied private paths. For
`--preflight-only` and the **normal game capture**, both `--rom-dir` and
`--workspace` remain mandatory. Mixed/partial paths fail closed before
any process or output creation. New synthetic tests cover two-path CLI,
compatibility, missing paths, symlink rejection and source-tree isolation.

A marker found in the linked ELF proves only presence of the compiled
literal data; it does not prove its runtime execution, genuine frame
alignment, original hardware VBlank or Nintendo Switch pixel parity.


## Stage 75 — keep private game ROMs away from MAME source and public builds

The private capture path preflight now rejects an original-game ROM folder
nested **inside** the disposable upstream MAME source/build tree, as well as
an enclosing ROM directory that contains that tree or the instrumented
executable. These are previously unguarded data-placement mistakes: a later
MAME build-tree archive, cleanup or copy could accidentally include licensed
ROM files, even though the game session itself remains local.

The two-path `--verify-build-only` check also refuses an instrumented MAME
executable located **inside this project's public Git checkout**, even if
the upstream MAME source tree lies elsewhere. A broad `git add` should not
be able to scoop up a modified emulator executable.

The checks take place before local game execution and before the private
capture directory, log or diagnostic report is created. They use only
filesystem path and type metadata, never read any ROM content, and preserve
the legacy ROM-free two-path build verification. Synthetic regression tests
cover each containment case and confirm there are no outputs on refusal.

Passing these checks is **filesystem isolation only**: it does not mean
original gameplay, CPS-1 hardware VBlank timing, or Switch renderer parity
was observed.


## Stage 76 — validate cumulative latch counts against nominal RGB/OBJ intervals

After the real upstream MAME 0.289 build compiled successfully with
session-aware strings visible in the **final linked ELF**, the next
preparatory step closes an integrity gap in the private six-frame audit.
The ordinary multistream analyzer compares per-interval callback deltas,
RGB pixels, OBJ slots and register words. The private launcher now also
runs `tools/mame_private_interval_consistency.py` before publishing its
final report. This independent metadata recalculation requires:

- all six nominal frame labels and five bounded interval entries agree;
- C++ observed cumulative callback counts are uint64, monotone and have
  exact adjacent differences matching the reported callback deltas;
- the zero-delta, multi-callback and changed-OBJ-without-callback frame
  lists exactly match recomputed cumulative counters and OBJ changes;
- every combined interval's RGB/OBJ/latch booleans and numeric fields
  match its source stream, and each aggregate total recomputes correctly;
- all six C++ sidecars are V2 OBJ-fingerprint-bound and session-tagged,
  with no claim of verified frame synchronization or pixel parity.

A contradiction is an **audit failure**: the completed private JSON is
never published, staged files are removed, and the original local capture
and emulator log remain untouched. A passing report includes only the
metadata-only `private_nominal_interval_consistency` summary, without
original RGB, buffered OBJ, ROM data, local file paths, SHA-256 digests
or the random session label. ROM-free synthetic regressions exercise
counter overflows/decreases, forged callback annotations, interval fields,
aggregates, labels, V2 session gate and the local final-publication block.

This is a check on redundant metadata emitted by the **same MAME process**.
Its success cannot authenticate commercial gameplay, physical VBlank
ordering, displayed frame age or pixel parity on Nintendo Switch.


## Stage 77 — fixed-vocabulary triage for the first private six-frame capture

The private MAME runner now adds a **small human-actionable summary** under
`private_capture_triage` after all previous integrity checks succeed.
The new `tools/mame_private_capture_triage.py` consumes only already
validated RGB, OBJ and latch interval summaries, plus the six-sample
same-process label check, cumulative-counter reconciliation and 54-file
source stability verification. It emits **fixed, non-sensitive reason codes**
for common follow-up investigations: all-black or static RGB, one-color
frames, absent OBJ changes, absent latch increments, apparently divergent
OBJ/callback activity or nonoverlapping RGB/OBJ changes.

Reports with no evident variation are marked
`LOW_INFORMATION_FOR_PRIVATE_CAPTURE_TRIAGE`. Contrasting observations
are marked `DIVERGENT_NOMINAL_STREAMS_REQUIRE_INSPECTION`; otherwise
co-variation is only `CO_VARIATION_OBSERVED_WITHOUT_TIMING_PROOF`. All
statuses remain diagnostic only, with explicit false active-gameplay,
original-game authenticity, hardware VBlank, frame-age, synchronization
and Switch pixel-parity claims. If there are no informational cautions,
the recommendation is to obtain an **independent VBlank timing reference**.
The report never copies arbitrary warnings, file paths, ROM/RGB/OBJ
bytes, image screenshots, session tokens or hash values from its inputs.

Triage is an additional fail-closed gate before exclusive publication
of the final private JSON. A malformed/contradictory integrity result
refuses to publish the final report; the private raw capture and log stay
untouched. ROM-free synthetic cases cover clean and divergent streams,
black/static/single-color frames, missing safeguards, malformed totals,
privacy redaction and failure after earlier audit gates. This is a
**decision aid**, not a substitute for actual private ROM gameplay or
independently timed original CPS-1 video evidence.


## Stage 78 — recompute every triage conclusion from detailed frame intervals

The previous Stage 77 decision aid accepted all seven aggregated change
counters as trusted inputs. A malformed report could change those totals
without changing the underlying five nominal intervals and receive a
different suggestion. Stage 78 closes this trust boundary: the triage module
now independently checks the exact nominal frame-label sequence, every
bounded RGB/OBJ/register/latch interval, the per-row derived boolean flags,
and **recalculates all seven totals** from those detailed observations.
It compares the RGB pixel series with per-row pixel counts and requires
the source's static/black/single-color classifications to match actual
per-frame color and nonblack-pixel counts. A contradictory cumulative-latch
summary is also refused. No recommendation is created for inconsistent data.

Regression fixtures now generate internally consistent synthetic RGB,
OBJ and callback series for clean co-variation, black/static video and
low-information captures instead of faking aggregate totals. Additional
negative tests mutate each total, row, counter summary, nominal label,
color classification or RGB series to verify fail-closed handling.
The normal private launcher already publishes its report only *after*
successful triage, so rejection leaves the final JSON unpublished.
No game ROM, RGB/OBJ binary data or raw capture-session tokens are
uploaded. The result remains a same-process diagnostic, **not** verified
gameplay, physical VBlank timing or original/Switch frame parity.


## Stage 79 — metadata-only first-run readiness check

Before spending time on a real private original-game session, the launcher
now offers a combined **ROM-free readiness command**:

```sh
python3 tools/mame_private_dino_session.py \
  --mame /private/mame0289/dino \
  --mame-tree /private/mame0289 \
  --rom-dir /private/owned-mame-roms \
  --workspace /private/empty-dino-capture \
  --check-launch-readiness
```

The 0700 workspace must already exist and be empty. The MAME source/tree,
user-owned ROM directory and workspace must remain outside this public
project and separate from each other. This dry-run first verifies the
instrumented `dino` driver using ROM-free `-listxml`, compiled CPS-1
session-aware object and **linked ELF probe markers**. It then checks only
filesystem metadata for a nonempty ordinary `dino.zip` archive or a
nonempty unpacked `dino/` game-set directory. Symlinked and empty
entries are refused to catch common placement mistakes. No archive is
opened or decompressed; no ROM bytes or private filenames are printed,
uploaded or hashed; no MAME game is launched and no capture output/log
is created. The returned `PRIVATE_DINO_LAUNCH_PREFLIGHT_ONLY` result
explicitly keeps ROM content integrity, complete set identification,
gameplay, synchronized callbacks and pixel parity unverified.

This is a convenience **presence check, not MAME's `-verifyroms`** and
cannot tell whether the user's private set is complete or usable. If it
passes, invoke the same command without `--check-launch-readiness` to
run the game privately in MAME. The ordinary capture retains its strict
six-frame, same-process session-label, source-stability and integrity
checks before publishing `dino-latch-diagnostic.json`. The resulting
local JSON report and `cps1-captures/` remain outside the public repo.
A run may fail at game startup even after metadata readiness succeeds.

Synthetic regressions verify zipped/unpacked layout, missing/empty/linked
entries, no original-ROM read, conservative output, bad ELF before entry
inspection, mutually exclusive modes and no filesystem side effects.
These synthetic results are **not a live original-game capture**.


## Stage 80 — path-safe failures for real private MAME sessions

The private launcher previously caught `OSError`, `ValueError` and similar
exceptions at its CLI boundary but **printed the original exception text**.
Python `FileNotFoundError` and permission exceptions may contain the
absolute pathname of a private original-game ROM, local MAME binary or
capture. A late file/read failure could therefore disclose private
machine paths to a copied console transcript or CI log.

The launcher now uses `tools/mame_private_cli_errors.py` to emit
**only fixed, path-free error codes and brief fixed guidance** on stderr.
Known errors are classified as invalid input, unverified MAME build,
invalid ROM layout, invalid workspace, failed MAME process, failed
capture audit or local filesystem error. Unknown exceptions are handled
at the CLI boundary without a traceback or exception string. The Python
API still raises normally for local debugging, and existing private
files/logs are retained. The CLI returns nonzero after any refusal
and never marks VBlank, gameplay or pixel parity verified.

ROM-free synthetic tests deliberately inject absolute private filenames,
simulated secret session tokens, permission errors and unexpected
runtime errors to verify the output does not echo original exception
messages, local paths, ROM data, or tracebacks. This change does not
run an original ROM or validate its integrity. For local inspection,
look inside the 0700 private workspace, not public GitHub logs.


## Stage 81 — safe, metadata-only post-failure capture progress report

A failed local MAME session can stop before collecting the six expected
nominal frames and their nine files each (54 total). Until now the strict
audit simply rejected missing or unexpected inputs, leaving the user to
manually compare private directory entries. The new standalone command
allows safe diagnosis **after** a failed run without retrying emulation:

```sh
python3 tools/mame_private_capture_progress.py \
  --workspace /private/empty-dino-capture
```

It requires the existing 0700 private workspace outside this repo. Only
the expected `cps1-captures/` directory is inspected. File bodies,
original ROMs, framebuffer pixels, buffers, JSON manifests, C++ sidecar
contents and the MAME log are **never opened**. It counts recognized
nominal frame entries, complete file-size sets, missing/short/oversized
files, unexpected entries, and the six Lua versus three C++ sidecars
per frame. The output uses only nominal frame labels, integer counts
and fixed investigation codes; filenames, ROM paths, session tokens
and digests are excluded. Unexpected symlinks, hardlinks, nonfiles or
oversized directory listings cause a conservative refusal.

Statuses include `NO_PRIVATE_CAPTURE_DIRECTORY`,
`NO_EXPECTED_PRIVATE_CAPTURE_FILES`,
`INCOMPLETE_PRIVATE_CAPTURE_FILE_SET`,
`INVALID_PRIVATE_CAPTURE_FILE_SIZES`,
`UNEXPECTED_PRIVATE_CAPTURE_ENTRIES`, and
`COMPLETE_FILE_SET_UNVERIFIED`. Even a file-size-complete set is
**not** an integrity-verified game: only the existing private full
capture launcher can check CRC32, OBJ FNV64, session binding and
stability. This post-failure tool writes no files and never asserts
authentic gameplay, hardware VBlank, sprite age or pixel parity.
ROM-free synthetic tests cover partial/complete sets, 54-count
arithmetic, missing frames, short files, symlinks and hardlinks,
privacy-sensitive filenames, bounded scanning and safe CLI errors.


## Stage 82 — locate Lua versus C++ coverage gaps by nominal frame

The read-only post-failure tool from Stage 81 now computes separate
**size-only completeness** for the six Lua files and three C++ video
probe files per nominal sample (frames 900, 902, 904, 906, 908, 910).
For each frame the report includes count of correctly sized Lua/C++
entries, whether the Lua manifest or C++ latch-count sidecar entry exists,
and a fixed coverage classification: both complete, Lua complete but C++
incomplete, C++ complete but Lua incomplete, or neither complete. Fixed
aggregate counts explain how many samples fall into each group. A manifest
or latch sidecar present without the other expected source entries is
highlighted solely as **incomplete file-set metadata**, never as proof of
callback write ordering, real frame age or video synchronization.

When only Lua files appear, the suggested local action names the
instrumented C++ video-update hook. When only C++ files appear, it names
the Lua `frame_done` hook. If both source families occur on different
nominal frames, it suggests comparing their frame coverage. Otherwise
the existing safe generic advice remains; invalid sizes, unexpected entries,
and complete-file-set notices retain their original higher priority.

No ROM/game content, framebuffer or OBJ buffers, SHA values, local paths,
private filenames, or capture logs are read or emitted by this tool.
Six-frame coverage is **never** proof of same-instant execution,
independent hardware VBlank, authentic gameplay or Nintendo Switch parity.
The strict 54-file audit and the private runtime launch remain separate.
New ROM-free regression tests cover Lua-only, C++-only, mixed/interleaved
samples, partial sidecars, invalid-sized components and preservation
of all conservative provenance flags.


## Stage 83 — bounded nominal-label coverage displacement hypotheses

A new ROM-free analysis component, `tools/mame_private_coverage_shift.py`,
compares the **presence and size-only completeness** of six Lua file sets
against six instrumented C++ file sets for nearby nominal labels. It
recomputes shared complete-frame counts for five possible C++-relative-to-
Lua sample-index offsets (-2, -1, 0, +1, +2). A candidate is presented
only when each stream has at least three complete size-only frame sets,
a single off-label offset matches at least three pairs, and its overlap
strictly exceeds the same-label count. Sparse, tied/ambiguous and ordinary
same-label distributions do not create a definitive offset.

The read-only post-failure progress report now includes
`nominal_coverage_shift_hypotheses` with bounded overlap scores,
an optional relative sample/frame-label offset, and explicit
`hypothesis_verified:false`. A strong, unambiguous off-label coverage
pattern suggests `INSPECT_LUA_CPP_NOMINAL_LABEL_COVERAGE_OFFSET` locally.
File-size corruption, unexpected entries and other stronger integrity
warnings always take precedence.

These are **filename/file-size availability correlations**, NOT emulator
callback timestamps. An apparent shift cannot establish the real
CPS-1 VBlank, buffered sprite age, game execution, original pixel values,
or Nintendo Switch parity. No ROM bytes, framebuffer, OBJ buffers, session
tokens, local paths or private warnings are accessed or emitted.
Synthetic tests exercise positive/negative shifts, complete/sparse
coverage, forged metadata, inspection priority and privacy.


## Stage 84 — leave-one-label-out sensitivity of nominal Lua/C++ gaps

The prior stage could report a single best nominal Lua-to-C++ file-coverage
offset without saying whether one missing sample would destroy that
tentative association. Stage 84 adds a **six-case leave-one-nominal-label-out
stress check** to `tools/mame_private_coverage_shift.py`. For each nominal
label, the checker excludes **both** Lua and C++ completeness evidence at
that same label, never renumbers or compresses surviving samples, then
recomputes all five [-2,-1,0,+1,+2] relative overlap scores. It requires
at least two remaining full-sized frames per source and two shifted pairs,
plus a strictly better unique off-label overlap, for a reduced sample to
retain the candidate. The main six-frame candidate continues to require
the prior stronger three-source-frame/three-pair threshold.

Only a candidate preserved in **all six** single-label omissions is tagged
`STABLE_UNDER_ALL_SINGLE_LABEL_DROPS_SIZE_ONLY`. Otherwise
`SENSITIVE_TO_SINGLE_LABEL_DROPS_SIZE_ONLY` supplies a separate count
of retained/changed/lost candidates and safe per-nominal-label observations.
No candidate means the sensitivity check is explicitly unassessed. With
a fragile candidate, the local progress tool now recommends
`REVIEW_SINGLE_LABEL_DROPOUT_SENSITIVITY`, not an unqualified offset
inspection; a stable candidate retains the prior generic
`INSPECT_LUA_CPP_NOMINAL_LABEL_COVERAGE_OFFSET` action.
Hard capture-integrity errors (unexpected entries or incorrect file sizes)
still take precedence over every possible gap hypothesis.

This sensitivity notion is **only about six discrete filename/size
observations**. Even a positive result does not prove independent timing,
original CPS-1 VBlank, buffered OBJ sprite age, active original gameplay,
original pixel accuracy, or Switch parity. The test suite covers
fragile and all-six-case-retained synthetic patterns, original cases with
no candidate, integrated guidance changes and no disclosure of ROM/file
paths, game pixels, metadata session secrets or hashes.


## Stage 85 — local MAME 0.289 `-verifyroms` before first game launch

Stage 79's metadata-only `dino.zip` presence check cannot tell whether
an owned ROM set contains the correct data for MAME. The first-run launcher
now offers an **opt-in private ROM-content verification** stage, backed
by the official MAME 0.289 `-verifyroms` frontend:

```sh
python3 tools/mame_private_dino_session.py \
  --mame /private/mame0289/dino \
  --mame-tree /private/mame0289 \
  --rom-dir /private/owned-mame-roms \
  --workspace /private/empty-dino-capture \
  --verify-private-romset-only
```

The 0700 workspace must already exist and be outside the public repo.
The launcher checks the genuine linked instrumented `dino` MAME ELF
and a nonempty `dino` game-set entry, then runs the **local binary**
with `dino -verifyroms -rompath <private-dir> -noreadconfig`. MAME itself
reads the ROM image locally and compares the set against its own known
checksums. Unlike ROM-free preflight, **this opt-in mode reads private
original game data inside the local MAME process**. Python never opens
the archive, and neither game emulation nor the Lua/C++ frame capture
runs. The verbose MAME audit output goes exclusively to
`dino-mame-private-rom-verification.log` in the private workspace;
the log is opened exclusively with 0600 permissions, never overwritten,
never included in a public CI artifact and never printed to console.

On a zero exit code, the conservative machine-readable status is
`PRIVATE_MAME_VERIFYROMS_EXIT_ZERO_UNATTESTED`: this means the
**local MAME subprocess** reported a successful exit, not that this
project independently authenticated the user's original set or ran the
game. A nonzero exit code, timeout, missing set or linked build failure
is rejected without launching the game or producing a final capture.
The CLI prints only a fixed safe reason code; details remain inside
the local private log. The optional local audit log does not block the
subsequent normal `dino` capture in the same workspace.

Synthetic tests emulate MAME exit outcomes, timeout, sensitive error
output, argv and environment separation, no game execution, log
permissions/overwrite safety and failure isolation. Public CI has **no
original commercial ROMs and does not execute an actual ROM audit**.
Consult the [official MAME -verifyroms documentation](https://docs.mamedev.org/commandline/commandline-all.html)
for more on what MAME checks. A successful ROM audit still cannot
verify genuine gameplay, physical VBlank, OBJ age or Switch pixel parity.


## Stage 86 — mandatory *same-invocation* ROM audit before the first private capture

Stage 85 added a separate local MAME `-verifyroms` diagnostic, but its
result was not linked to the subsequent real-game capture invocation. To
avoid trusting a historical audit (which might refer to a different MAME
binary, modified set, or user action), the private launcher now supports a
**single opt-in guarded launch**:

```sh
python3 tools/mame_private_dino_session.py \
  --mame /private/mame0289/dino \
  --mame-tree /private/mame0289 \
  --rom-dir /private/owned-mame-roms \
  --workspace /private/new-empty-dino-workspace \
  --verify-private-romset-before-capture
```

Within this one local invocation, the launcher verifies the linked MAME
0.289 `dino` build, checks the private set's filesystem entry, then
executes that **same local MAME binary** in `dino -verifyroms` mode,
with `-noreadconfig`. As in Stage 85, MAME itself reads private original
game bytes, while Python never opens them. Details go exclusively into
a fresh local 0600 ROM-verification log. Only a zero MAME exit code
permits a **second**, separately labeled MAME `dino` game process and
the usual six-frame Lua/C++ collection. The game command also uses
`-noreadconfig` so local MAME configuration files cannot silently
override its declared capture settings.

A missing/invalid set, MAME failure/timeout, identity mismatch or existing
verification log halts the guarded operation before generating a game
session token, private capture folder or final diagnostic report. The
log is never clobbered or echoed to GitHub. A successful local capture
records `local_mame_verifyroms_exit_zero_before_capture: true`
in its **private-only** completion report; ordinary unguarded captures
record `false`. This boolean means only that the local MAME audit
subprocess exited successfully. It **does not authenticate original
game ownership or execution**, guarantee the ROM bytes are immutable
between audit and gameplay, or establish CPS-1 physical frame age,
video parity or a working Nintendo Switch game.

The original `--verify-private-romset-only` option remains available;
it cannot be combined with the new guarded-launch option. New ROM-free
synthetic tests verify process sequence, secure private log, no token
on audit, timeout/failure refusal before capture-folder creation,
stale-audit rejection, lack of false claims in the unguarded path,
CLI privacy and mutually exclusive modes. **No original ROM data is
run in public GitHub CI.**


## Stage 87 — public-repository guard against accidental original ROM upload

**Never push original `dino.zip`, original CPS-1 assets, captures,
private MAME logs or modified emulator binaries to the public GitHub repo.**
A locally owned original image does not by itself grant permission to
redistribute copyrighted arcade game data. Keep user-owned ROMs in a
separate private directory and use the stage-86
`--verify-private-romset-before-capture` command locally.

The code-only repository now includes a privacy guard for Git's **staged
index** (not the possibly different files in the working tree):
```sh
python3 tools/check_public_tree_rom_free.py
```
It rejects archived ROM/container extensions including `.zip`, `.bin`,
`.chd`, `.gen`, `.iso`, console executables `.nro`/`.nsp`, emulator
binaries, directories named `roms/` or `cps1-captures/`, non-source
extensions, source blobs larger than 256 KiB, symlinks, obvious archive
magic, NUL-filled non-source data and Git LFS pointers. A ROM archive
forcibly staged through `git add -f` is still rejected. The fixed
machine-readable report prints **only rejection counts**, never staged
filenames, paths, ROM bytes or Git hashes.

Optionally enable the included local pre-commit hook:
```sh
git config --local core.hooksPath .githooks
```
This prevents an accidental **local commit** (unless the hook is
disabled/bypassed). The new `Public repository ROM-free privacy gate`
GitHub Actions workflow runs for every push and pull request, including
docs changes. Importantly, **CI runs only after GitHub already receives
the pushed commit**, so it cannot prevent initial disclosure. The local
hook and careful manual staging are essential; a scan cannot prove
copyright licensing or the absence of cleverly disguised game data.
Previously pushed history is not scanned or purged. Original ROM tests
remain local, outside public GitHub CI.

Synthetic tests use fabricated miniature archive signatures and fake
game filenames only. Approved cover artwork is untouched.


## Stage 88 — guard original ROM entry metadata from audit through report publication

A successful MAME `-verifyroms` exit followed by a later `dino` game
launch did not previously detect when a local ROM archive was swapped or
edited **between** those two subprocesses. Added a bounded, byte-free
ROM metadata snapshot to the guarded Stage 86 launch path.

`tools/mame_private_rom_metadata.py` inspects ordinary `dino.zip`
archive metadata or the bounded top-level unpacked `dino/` entry set.
It retains private filenames, inode identities, file lengths, link counts,
modification/change timestamps and file types **in process memory only**.
It does not open the ROM contents, compute or print ROM hashes, or store
metadata in the final report. Links, replaced files, added/removed
unpacked entries or nested unpacked directories are rejected in this
guarded mode. A new snapshot is taken **before** the MAME ROM audit and
compared after the audit (before allocating any game capture files),
after the real local game process, and immediately before publication
of the final private diagnostic report.

If metadata differs, the operation fails closed, keeps the private audit
and capture logs for local examination, and **never publishes a success
report**. The protected-path private report fields
`private_rom_entry_metadata_stable_during_capture` (true for completed
guarded sessions, false for unguarded sessions) and
`private_rom_metadata_stable_after_audit` (verify-only mode) are only
statements about filesystem metadata; **no ROM bytes are hashed by
Python**. This is not an atomic filesystem lock, tamperproof guarantee,
proof of identical input bytes, independently authenticated game, physical
CPS-1 VBlank or Nintendo Switch pixel parity.

Synthetic regression tests cover overwritten ROM archives during MAME
verification and during simulated gameplay, unchanged guarded sessions,
and deliberately unguarded captures without false stability claims.
The code and CI remain ROM-free; no actual commercial game runs on GitHub.


## Stage 89 — ROM SHA-256 content stability inside private guarded MAME sessions

The metadata-only stability guard introduced in Stage 88 could miss
changes if an adversary or filesystem restored size and timestamps.
Stage 89 adds a **bounded, private SHA-256 byte comparison** to the
opt-in local original-game ROM verification and guarded capture modes.

`tools/mame_private_rom_content.py` streams up to 256 MiB of ordinary
`dino.zip` or flat unpacked `dino/` game-set bytes in chunks of 1 MiB,
using no-follow file opening, fstat checks before/after each read,
plus the Stage 88 name/type/inode/size/time snapshot. It keeps SHA-256
digest **bytes only in RAM**, never prints, persists, shares or adds
a hash/path/file content to either the private capture report or CI.
The check is repeated after the MAME `-verifyroms` subprocess,
after local game exit and immediately before private success-report
publication. Any mismatch prevents game execution or report publication.
The separate verify-only mode now also requires stable byte content.

**Disclosure of changed semantics:** guarded and verify-only Python
launches now intentionally **read the private ROM bytes locally**
for stability hashing, in addition to the MAME process reading the
original set. The old verify-only field `rom_bytes_read_by_python:false`
is now **true**, and new bool-only report fields include
`private_rom_content_sha256_stable_after_audit`,
`private_rom_content_sha256_stable_during_capture` and
`private_rom_bytes_read_by_python`. Unguarded, preflight-only and
build-only modes do not read private ROM contents or falsely claim
byte stability.

This establishes only content stability across sampled times:
hashing cannot prevent a malicious file swap between observations,
nor prove game ownership, official provenance, physical CPS-1 VBlank,
buffered OBJ sprite age or Switch image parity. Public CI exercises
only fabricated synthetic byte strings and never checks genuine
commercial game files or uploads any game material.


## Stage 90 — safe inline metadata diagnosis after the first failed local capture

Before Stage 90 a local `dino` session failure gave only a fixed refusal
reason, requiring a second manual
`tools/mame_private_capture_progress.py --workspace ...` invocation
to learn which of the six nominal frame groups was incomplete.
The private launcher now offers an **opt-in** single-command
read-only error summary:

```sh
python3 tools/mame_private_dino_session.py \
  --mame /private/mame0289/dino \
  --mame-tree /private/mame0289 \
  --rom-dir /private/owned-mame-roms \
  --workspace /private/new-empty-dino-workspace \
  --verify-private-romset-before-capture \
  --diagnose-failed-capture
```

On success the existing full verified-private-diagnostic path is
unchanged. On failure, one machine-readable stderr JSON object
contains the existing **safe fixed reason code** plus an optional
`capture_progress` section. That section is derived from the
Stage 81–84 metadata-only progress scanner and then projected through
strictly enumerated fixed status/action codes, bounded aggregate
counts and six nominal Lua/C++ name-and-size availability rows.
Unknown freeform keys, exception messages, local ROM paths, original
filenames, SHA digests, and session IDs are **never copied out**.
If the progress scan itself refuses a symlink, invalid workspace,
unexpected shape or oversized directory, the entire progress section
falls back to fixed `PRIVATE_CAPTURE_PROGRESS_REFUSED`. A failed
emulator subprocess with an empty capture directory reports zeros and
the safe MAME startup-log investigation code.

The additional diagnostic is only allowed with a real game-capture
attempt, never with ROM-free preflight, build verification or standalone
ROM verification. It never opens captured file **bytes**, ROM bytes,
MAME logs or manifests; these remain in the isolated workspace.
The opt-in guarded launcher still hashes user-owned ROM bytes
privately for Stage 89 **before** this postmortem step when requested.
Even a complete metadata-only file set never proves real gameplay,
verified VBlank order or Switch pixel parity.

ROM-free tests exercise interrupted original-MAME-style processes,
absent/partial/synthetic-complete captures, unsafe symlinks and paths,
malicious extra text fields, broken progress scans, unchanged CLI default
and incompatible option combinations.


## Stage 91 — optional automatic clean MAME exit after six private captures

The Lua script previously stopped collecting once the six nominal
samples (900, 902, 904, 906, 908, 910) were present but left MAME
running until a person closed the application or the Python process
timed out. A private first-run experiment therefore could not finish
unattended even if the files had already been collected.

Use **explicit opt-in** `--auto-exit-after-capture` with the guarded
first-run command:

```sh
python3 tools/mame_private_dino_session.py \
  --mame /private/mame0289/dino \
  --mame-tree /private/mame0289 \
  --rom-dir /private/owned-mame-roms \
  --workspace /private/new-empty-dino-workspace \
  --verify-private-romset-before-capture \
  --diagnose-failed-capture \
  --auto-exit-after-capture
```

Only the actual game subprocess receives
`CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE=1`. An inherited variable is
**removed** for default interactive game runs, and no auto-exit flag
is passed to the initial `-verifyroms` audit. The Lua script never
calls `manager.machine:exit()` before collecting six successfully
written five-component binary and manifest bundles. Once frame 910's
manifest has been closed, it waits until a **subsequent** frame_done
callback reports a strictly larger nominal frame number before
scheduling exactly one exit. This leaves a conservative extra frame
for the instrumented C++ source, but is NOT proof of callback order,
buffered OBJ age or VBlank alignment. MAME 0.289 documents
`running_machine:exit()` as a scheduled exit, not an immediate
exception. Any nonzero exit or incomplete C++ set is still refused
by the launcher, and no verified success report is created.

The default behavior is unchanged: manual exit remains supported.
Auto-exit is rejected in preflight-only, build-only, readiness and
verify-ROM-only modes. The private success report records only the
Boolean `auto_exit_after_capture_requested` and never claims that
the emulated gameplay was authentic. No original ROMs or captures
are placed in public GitHub Actions.

MAME Lua API: https://docs.mamedev.org/luascript/ref-core.html


## Stage 92 — refuse premature auto-exit until all nine Lua/C++ files per sample are size-ready

Stage 91 initially scheduled an exit on the first callback after
Lua finished its sixth captured sample. That did not check whether
the C++ video-update probe had actually written its buffered OBJ,
render-register and latch-count sidecars at all six nominal labels.
The first real capture might have shut down with C++ files missing.

The `--auto-exit-after-capture` Lua path now checks the **full 54-file
set** for all sample labels 900, 902, 904, 906, 908 and 910:
the five fixed-size Lua binary components, a bounded Lua manifest
(1..16384 bytes), two fixed-size C++ components (128 and 2048 bytes),
and the bounded C++ latch sidecar (1..128 bytes). It uses Lua
`io.open(...,'rb')` and `seek('end')` to check size **without reading
any file content**. The game exit is requested only after *two later
callbacks* have observed every file with a valid size; under ordinary
complete conditions this is nominal frame 912, not frame 911.

If the C++ probe is absent, late, partially written or has an
unexpected size, the Lua callback holds off automatic exit up to
120 additional nominal frame numbers after the last Lua sample
(frame 1030). It then requests an exit so that the local Python
launcher can **reject the incomplete capture with the ordinary
strict CRC/FNV/session/ROM checks** and its optional safe failure
progress diagnostic; it does not wait indefinitely until the launcher
timeout. Manual-mode runs never inspect C++ sidecars or auto-exit.

The size probes are **metadata evidence only**, not proof of file
durability, real shared VBlank, independent C++ timing, original game
authenticity or Nintendo Switch pixel parity. The launcher still
requires the existing complete Python verification *after* MAME stops.
Synthetic Lua 5.4 MAME API regressions create artificial C++ files
covering immediate completion, delayed final sidecar, permanently
missing sidecars and incorrect final sidecar size. No commercial ROM
or game frame is used in the public repository.


## Stage 93 — local Lua auto-exit markers without exposing MAME logs

Stage 92 may end the emulator once two subsequent frame_done callbacks find all 54 Lua/C++ capture entries at acceptable sizes, or after the 120-frame grace limit if sidecars never become ready. Stage 93 distinguishes those Lua *reported reasons* in the existing private session log with exact fixed lines:

- `CPS1_DINO_AUTO_EXIT_V1_READY_54_SIZE_ONLY` — size-ready condition observed twice;
- `CPS1_DINO_AUTO_EXIT_V1_GRACE_INCOMPLETE_SIZE_ONLY` — grace interval exhausted.

The opt-in `tools/mame_private_auto_exit_evidence.py` scanner observes the local game log only after MAME has ended, only when the operator requested `--auto-exit-after-capture`. It limits scanning to 16 MiB, rejects symlinks, hardlinks and changing file metadata, and requires a unique, complete marker line. It returns safe, enumerated status codes for ready, grace, ambiguous, absent or unsafe logs. It never includes local paths, ROM names, session identifiers, hashes, original frame bytes or any raw log text in its output. The success report stores `auto_exit_log_observation` as safe diagnostic metadata; the opt-in `--diagnose-failed-capture` stderr JSON can also include the same code after a failed game run. Default manual sessions do not read the private log.

**Caution:** This is the Lua callback's logged message, not an independent verification of why the MAME process ended, original-game authenticity, VBlank timing, buffered OBJ age, file-content integrity or Nintendo Switch parity. Even the ready code cannot bypass strict private CRC/FNV/ROM stability checks or turn a failed/incomplete capture into success. Public tests use only synthetic log lines and fake game processes; no original ROM or private game log is uploaded to GitHub.


## Stage 94 — reconcile private Lua exit markers with post-run six-frame coverage

A Stage 93 fixed Lua exit message alone could suggest all 54 files were size-ready even if the final private filesystem inspection showed missing, invalid or unexpected capture entries. Stage 94 adds `tools/mame_private_auto_exit_reconciliation.py`, a small, **ROM-free and file-I/O-free** categorical crosscheck. It compares the two fixed marker observations (`READY` versus `GRACE`) with the *post-run* six-row, 54-file size-only scanner result, or with the strict completed CRC/FNV/session audit in a successful session. It will explicitly report `READY_MESSAGE_CONTRADICTS_POST_RUN_FILES` or `GRACE_MESSAGE_CONTRADICTS_POST_RUN_FILES` when those independent-looking metadata observations differ.

This reconciliation never overrides existing strict capture failures or creates a success report on its own. Missing/unreadable/ambiguous markers, malformed counts, unsafe capture paths and missing source frame rows produce a fixed **unavailable/not usable** status rather than an inference. Successful private auto-exit captures place `auto_exit_post_run_reconciliation` in their private final report; an opt-in failure using both `--auto-exit-after-capture` and `--diagnose-failed-capture` includes the same fixed diagnostic in its single safe stderr JSON. Manual launches skip the reconciliation and retain a null report field. No filenames, original ROM bytes, framebuffer data, OBJ words, private hash digests, session IDs or raw log messages are disclosed.

A `READY_MESSAGE_AGREES_WITH_SIZE_ONLY_FILES` result only means the observed fixed Lua message agrees with final *file size evidence*. It is **not** independent confirmation of Lua/C++ callbacks, original CPS-1 VBlank, genuine active game frames, hardware timing or Nintendo Switch pixel parity. The first run with the user-owned original `dino` still requires the locally built instrumented MAME executable and private ROM; public CI remains entirely synthetic.


## Stage 95 — a one-command private first-capture handoff

For the first local original-game capture, a new wrapper uses a
ROM-free **check-only default** and an explicit **--run** flag.

First prepare a fresh, empty private workspace OUTSIDE this public
GitHub repository (mode 0700) and check prerequisites without opening
original ROM bytes:

~~~sh
umask 077
mkdir -m 700 /private/new-empty-dino-workspace
python3 tools/mame_private_first_capture.py \
  --mame /private/mame0289/dino \
  --mame-tree /private/mame0289 \
  --rom-dir /private/owned-mame-roms \
  --workspace /private/new-empty-dino-workspace
~~~

Replace every example path with its *local* value. The binary must be
a genuine locally built instrumented MAME 0.289 dino executable,
not the Switch NRO technical bootstrap. The ROM directory must contain
the original set legally possessed by the operator. This default
command checks only path isolation, linked MAME identity and game-set
presence metadata. It does NOT read original ROM bytes, emulate the
game or create any frame capture. Its short JSON status is
PRIVATE_DINO_FIRST_CAPTURE_READINESS_METADATA_ONLY.

Only when you choose to start a real *local* game run, repeat the
same command with --run appended. This performs the same-invocation
MAME -verifyroms ROM audit, private SHA-256 input stability checking,
six Lua/C++ samples and optional size-based automatic exit, then
requires the existing strict 54-file CRC/FNV/session and interval
validation. Original ROM bytes are read locally by Python and MAME
only in this explicit run mode.

The helper prints **one small whitelisted JSON report**, with
schema PRIVATE_DINO_FIRST_CAPTURE_HANDOFF_V1. On strict structural
capture success it returns PRIVATE_SIX_FRAME_STRUCTURAL_AUDIT_PASSED
plus fixed counts and statuses; on refusal it returns
PRIVATE_DINO_FIRST_CAPTURE_REFUSED with a fixed safe reason, bounded
file counts and fixed Lua-exit diagnostic codes if available.
No original filenames, user directory paths, framebuffers, buffered
OBJ bytes, SHA digests, MAME log text or session tokens are echoed.

**Only paste the small emitted JSON into ChatGPT** for troubleshooting.
Do not upload private commercial ROMs, logs, game capture directories
or detailed diagnostic manifests to a public GitHub repository.
Even a successful structural audit does not prove original-game
authenticity, physical CPS-1 VBlank, framebuffer pixel parity or
completed Nintendo Switch gameplay. Public CI only uses synthetic data.

## Stage 98 — private real-ROM graphics parity against native Switch decoder

The user-owned original dino ZIP now has a separate local-only validation
path that does not depend on the blocked MAME qsound_hle device or
incompatible ioc1.ic1 PLD. This is **graphics decode parity only**;
no emulated gameplay, VRAM palette, VBlank ordering or Switch framebuffer
pixel parity is claimed.

On the operator machine, with gcc and the original ROM archive available
outside the repository:

~~~sh
python3 tools/cps1_private_native_tile_parity.py /private/owned/dino.zip
~~~

This locally reads exactly eight 512-KiB graphics lanes from the ZIP
and interleaves them into 4 MiB **in memory only**. It compiles the exact
portable source/cps1_tile.c used by the technical Switch NRO into a
temporary host shared library. A separate Python planar reference
decoder checks 16x16 4-bit pen indices on a fixed beginning, ending,
every-64th, and pseudorandom set covering both graphics banks.
Native invalid-code and truncated-region refusals are also checked.
Only bounded counters and fixed success/refusal codes appear in JSON.
No raw game data, commercial ROM archive, pixel values, SHA digest,
original filename or private path is emitted or committed to GitHub.

On the original ZIP supplied for this project, an isolated private
run sampled 1,510 tile codes (386,560 pen-index pixels) with zero
C/Python mismatches; all 16 possible 4-bit pen values appeared and
native error-path bounds checking refused invalid requests. This
proves equivalence **on the tested tiles and indices**, not game
authenticity, original runtime colors, sprites, CPS-1 VBlank,
or a playable Nintendo Switch title.

Public GitHub Actions runs new tests with fabricated eight-lane
graphics archives only: complete synthetic parity, deliberately
corrupted reference decoder, missing/duplicate/truncated ROM entries,
failed compiler redaction, no private output data, and bounds.

## Stage 104 — inspect the known original-ROM MAME blockers locally

The new opt-in tool gives a **fixed-schema, path-free and hash-free**
diagnosis of the two specific blockers previously observed while
attempting to launch the privately held World 930201 set with MAME
0.289: the `ioc1.ic1` catalog size/CRC mismatch and absence of a
separately supplied `qsound_hle.zip` archive containing a
`dl-1425.bin` member. This status is not evidence of an original
game boot or a new -verifyroms result.

Run in your own private machine with a standard MAME ROM directory,
outside the public checkout:

~~~sh
python3 tools/mame_private_rom_blocker_triage.py --rom-dir /private/owned-mame-roms
~~~

It reads **ZIP central-directory entries only**, comparing the
size/CRC headers of all 28 expected game members with the pinned
MAME 0.289 World 930201 catalog and checking for the named QSound
device member in the separate archive. It does not extract or read
game ROM member payloads, or create files. Results include only
aggregate counts, conservative booleans and static action codes,
never private paths, ROM member names, ZIP CRCs, extracted sprites,
original game data or hashes.

Caution: ZIP central-directory CRCs can be fabricated and do not
prove that the compressed payload is correct. Even a full
28/28 header match and observed QSound member does **not**
establish archive validity, device ROM authenticity, a complete
MAME clone/BIOS dependency layout or actual MAME acceptance.
MAME can also support alternative set layouts that this deliberately
narrow, conventional two-ZIP check does not enumerate. A returned
success classification means only that these **particular known
metadata blockers were not observed**. Before real capture, run
genuine MAME `dino -verifyroms` on the privately held set and
require its exit code 0; do not share ROM files or emulator dumps.

Public CI tests this CLI against *fabricated ZIP central-directory
metadata* and deliberate corrupt/missing/linked entries only. It
never checks in or runs a real original game ROM, and does not
claim VBlank, game video capture or Switch gameplay parity.

## Stage 105 — exact QSound HLE archive-header check for MAME 0.289

Stage 104's presence-only QSound check was insufficient: a ZIP can contain
`dl-1425.bin` but still fail MAME's mandatory ROM audit. Verified directly
against the pinned **MAME 0.289** source
[`src/devices/sound/qsoundhle.cpp`](https://github.com/mamedev/mame/blob/mame0289/src/devices/sound/qsoundhle.cpp),
its `ROM_LOAD16_WORD` reads 0x2000 bytes followed by `ROM_IGNORE(0x4000)`.
The **complete original ROM file** therefore occupies **0x6000 / 24,576
bytes**, and its public catalog CRC is **d6cf5ef5**. Using only
0x2000 bytes would give a false match for the loaded DSP subsection.

The local tool now requires the **exact 24,576-byte length and CRC32**
from `qsound_hle.zip` central-directory metadata before reporting the
known QSound header blocker absent. It distinguishes three states
without exposing ZIP contents or private hashes:

- Archive or required member absent.
- Member present, but size or CRC header differs.
- Member header size and CRC both match the pinned catalog.

An absent/bad PLD combined with a bad QSound header is explicitly reported
as two simultaneous dependencies requiring local investigation.
Tests replace the real game/device files with entirely **synthetic ZipInfo
headers**, including a deliberately truncated 0x2000-byte device entry
and altered CRC. A matching header is **not a trustworthy payload
checksum**: ZIP directory CRC data is untrusted until genuine MAME
`dino -verifyroms` has processed the privately held assets. No actual
game launch, audio validation or MAME VBlank/pixel proof is claimed.

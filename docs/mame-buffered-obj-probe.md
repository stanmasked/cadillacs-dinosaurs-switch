# Stage 41 — opt-in MAME 0.289 buffered CPS-1 OBJ probe

## Why the Lua capture is still incomplete

The MAME source for `dino` **CPS-1** allocates `m_buffered_obj` with
`m_obj_size / 2` 16-bit words (`m_obj_size = 0x0800` bytes), and its
`cps1_objram_latch(int state)` copies *unlatched* `m_obj` into this
**2048-byte VBlank-latched** buffer. The video renderer reads
`m_buffered_obj`, not arbitrary mutable graphics RAM.

Ordinary MAME Lua memory shares cannot directly read this private
`cps_state` buffer. Guessing the sprite list or reading mutable RAM
after the render would not establish a valid pixel-parity reference.

MAME version: **0.289**, file `src/mame/capcom/cps1_v.cpp`,
upstream Git blob SHA-1:
`c1b5e3867824d0d1877b981142db7741346d2c55`.

## Private, opt-in source instrumentation

The ROM-free tool `tools/mame_obj_source_probe.py` reads the user's
*unmodified, checked-out* MAME 0.289 source. It requires the exact
upstream Git blob SHA and unique video-update anchors. It writes a
**new C++ file only** with `open('xb')`; it never overwrites the
original source or attempts to compile/run MAME.

```sh
python3 tools/mame_obj_source_probe.py \
  /private/mame-0289/src/mame/capcom/cps1_v.cpp \
  --out /private/cps1_v.objprobe.cpp
```

For an optional private local experiment, copy the generated file into
**a separate disposable MAME 0.289 build tree**, replacing only that
tree's `src/mame/capcom/cps1_v.cpp`, and build/run its `dino`
driver with the existing `tools/mame_cps1_capture.lua`. Use a fresh
`cps1-captures` directory in the MAME process's working directory.
Keep modified MAME binaries, patches with proprietary game content,
all ROMs and the resulting capture data private.

The generated instrumentation adds a narrow read of
`m_buffered_obj[0..1023]` inside `screen_update_cps1`, immediately
after `find_last_sprite()`, before the layer renderer. It uses the
emulator screen's `frame_number()`, restricts to `dino`, samples the
same six nominal indices 900, 902, 904, 906, 908, 910 as the Lua
recorder and writes big-endian
`frame-XXXXXXXX.buffered-obj-be.bin` files containing exactly
1024 16-bit words. An existing probe file is not overwritten.
The probe does **not** modify m_buffered_obj or game registers.

No Switch executable or integrated MAME build is provided in GitHub.
A generated source copy is **not evidence that a patched MAME binary
was successfully compiled or run**. The script must be reviewed against
the user's installed MAME source/build configuration.

## Inspecting OBJ without falsely confirming synchronization

First import the ordinary Lua reference capture locally as before:

```sh
python3 tools/mame_capture_import.py cps1-captures frame-00000900 \
  --out-dir local_outputs/mame-reference
```

Then attach the experimental buffered OBJ bytes:

```sh
python3 tools/mame_obj_probe_import.py \
  local_outputs/mame-reference/frame-00000900.partial-snapshot.json \
  cps1-captures/frame-00000900.buffered-obj-be.bin \
  --out local_outputs/mame-reference/frame-00000900.obj-diagnostic.json
```

The adapter requires **exactly 2048 bytes**, checks its canonical
filename against `reference_frame`, decodes 1024 big-endian words,
preserves the first 0xFFxx OBJ end-marker position (if present),
records the raw probe's SHA-256 (integrity metadata, **not** proof of
provenance), and returns a new diagnostic snapshot without touching
original files.
Every output is labeled:

- `buffered_obj_source: MAME_0289_CPP_OBJ_PROBE_UNSYNCED`
- `obj_probe_frame_alignment: NOT_INDEPENDENTLY_VERIFIED`
- `pixel_parity_eligible: false`

The existing native `scene.bin` exporter continues to **reject**
such snapshots, despite containing a candidate real OBJ buffer.

## Mandatory verification before authenticity claims

1. Build **actual** MAME 0.289 from the disposable instrumented tree and
   verify output lengths, marker semantics, endianness and compilation.
2. Independently reconcile frame counters between
   `screen_update_cps1` and Lua `register_frame_done` (some display
   pipelines may increment counters between these hooks).
3. Verify VBlank-latch age, register/scroll/palette timing and absence of
   subframe video state changes before attempting renderer parity.
4. Compare the exact reconstructed 384×224 frame against the native
   MAME screen, with no unproven frame offset or artificial sprite list.
5. Only after all checks, explicitly design a separate, versioned
   **verified** snapshot provenance format. Do not rewrite the original
   partial-snapshot manifest to claim parity.

The generated source instrumentation is restricted to exactly six
test frames; if the capture window changes, both the probe and Lua
script must be adjusted and reviewed together. The source uses
single-process presence checks, not atomic multi-process file locking.

## Offline tests and limitations

- Ten ROM-free unit tests exercise unique source injection, buffered
  versus unlatched read, six-frame range, byte order, source SHA check,
  refusal to overwrite or modify originals, and fail-closed anchors.
- Ten additional tests exercise 2048-byte decode, marker scanning,
  strict frame naming, unchanged source JSON, export safety and exclusive
  output writes.
- The upstream MAME 0.289 `cps1_v.cpp` **blob and source anchors were
  inspected directly**: expected blob SHA and both unique anchors match.
- A standalone C++17 `-Wall -Wextra -Werror` compilation with
  synthetic MAME-like stubs exercised the **probe-writing code pattern**:
  frames 900/902 yielded two 2048-byte big-endian files, re-running
  frame 900 left it untouched, and frame 901 created no file.
  This was **not a build of the real MAME driver**.
- **Not yet validated:** compiling the generated C++ in MAME, running a
  genuine `dino` gameplay session, or full GitHub CI (issue #20).

No copyrighted ROM graphics, game frames or derived assets are committed.


## Stage 42 — compare CPS-A/B registers across two capture hooks

The generated source probe now also writes a **128-byte sidecar** for
each permitted dino frame:

`frame-XXXXXXXX.render-regs-be.bin` consists of exactly 32 big-endian
CPS-A words followed by 32 big-endian CPS-B words, read inside
`screen_update_cps1` at the *same hook* as the buffered OBJ. If either
the OBJ or register file for that frame already exists, the probe
refuses to overwrite or create a half-new pair; the sidecar is written
only after the OBJ output is closed successfully. Interrupted writes
remain possible and are rejected by length validation.

The original Lua capture independently writes the 64-byte
`frame-XXXXXXXX.cps-a-be.bin` and `.cps-b-be.bin` after the screen
has been rendered. Compare these independent copies:

```sh
python3 tools/mame_obj_register_audit.py \
  local_outputs/mame-reference/frame-00000900.partial-snapshot.json \
  cps1-captures/frame-00000900.buffered-obj-be.bin \
  cps1-captures/frame-00000900.render-regs-be.bin \
  cps1-captures/frame-00000900.cps-a-be.bin \
  cps1-captures/frame-00000900.cps-b-be.bin \
  --out local_outputs/mame-reference/frame-00000900.alignment-audit.json
```

The ROM-free auditor requires all input filenames to identify the same
canonical frame, the OBJ to be exactly **2048 bytes**, the render
register sidecar to be exactly **128 bytes**, and each Lua register
block to be exactly **64 bytes**. It compares all 32 big-endian
16-bit words separately for CPS-A and CPS-B, and reports the number
of mismatches plus up to eight word indices for diagnosis. The output
includes SHA-256 of the OBJ and 128-byte register probe data; it
does **not** include or publish original game RAM.

A successful audit can show that the **register values are equal** at
both sampling points, but this is *necessary, not sufficient* evidence
of frame alignment: neighboring frames often share unchanged register
values, and framebuffer pixel timing and the VBlank sprite-latch age
are still unverified. The audit therefore **always** reports
`frame_sync_verified:false` and `pixel_parity_eligible:false`,
even with 64/64 equal register words. A mismatch is a concrete
difference between the two captures and should be investigated for
midframe register writes, measurement time, wrong pairing, or errors.

Do not use the report to bypass the native scene exporter's incomplete
capture guard. The existing project `main` stays ROM-free and the
probe remains a private, opt-in MAME source experiment.

**Validation:** A locally compiled independent C++17 test stand with
`-Wall -Wextra -Werror` exercised the register sidecar code pattern:
it emitted 2048-byte OBJ files and 128-byte register files for
frames 900 and 902, skipped frame 901, preserved the four sample
register words in big-endian order, and did not overwrite frame 900.
This does not compile the real MAME 0.289 source. **The exact
committed Python auditor and its eight-test module were copied into a
local isolated test environment, their Git blob SHA-1 values checked
against GitHub, and all 8/8 tests passed** (including strict output
refusal, mismatched word positions, and permanently ineligible parity).
An additional C++-probe source test is committed but has not run in
GitHub CI. Full GitHub Actions execution remains blocked by issue #20.


## Stage 43 — bind Lua register evidence to capture CRC32

The Stage 42 register audit previously compared the private C++-probe
CPS-A/CPS-B sidecar with the two raw Lua register files but did not
verify whether those Lua bytes still matched their imported capture.
An altered file of the same length could therefore generate a
misleading `registers_match_exactly: true` result.

`tools/mame_obj_register_audit.py` now uses the `capture_file_crc32`
field supplied by the checksum-aware
`tools/mame_capture_import.py` from [PR #25](https://github.com/stanmasked/cadillacs-dinosaurs-switch/pull/25):

- When the field is present, require **exactly five** lowercase
  eight-digit CRC32 hex entries with the expected file names.
- Recalculate CPS-A and CPS-B CRC32 from the **actual 64-byte Lua input
  files** and fail before writing the audit if either differs.
- Identify two distinct facts in the JSON:
  `registers_match_exactly` records byte-for-byte equality between
  hooks, whereas `cross_hook_register_evidence_with_crc` is true
  only when that equality **and** both Lua input-file CRC checks hold.
- `lua_register_integrity.verified_register_files` is **2** for
  accepted checksum-bearing input. The three other components are
  *not reread or revalidated* by this cross-hook tool.
- Older partial snapshots **without** `capture_file_crc32` remain
  diagnostic: the raw register comparison still runs, but the CRC
  evidence flag is false and the status is
  `NO_CRC32_IN_PARTIAL_SNAPSHOT`. Explicitly malformed/empty/null
  checksum fields fail closed.

For stronger checks, supply `--require-register-crc` to the Stage 42
command. With that flag, missing CRC evidence causes exit code 2 and
**no audit output is created**. It does not weaken other file-identity,
buffer-size or no-overwrite validation.

For example:

```sh
python3 tools/mame_obj_register_audit.py \
  local_outputs/mame-reference/frame-00000900.partial-snapshot.json \
  cps1-captures/frame-00000900.buffered-obj-be.bin \
  cps1-captures/frame-00000900.render-regs-be.bin \
  cps1-captures/frame-00000900.cps-a-be.bin \
  cps1-captures/frame-00000900.cps-b-be.bin \
  --out local_outputs/mame-reference/frame-00000900.crc-audit.json \
  --require-register-crc
```

**Requirements:** This audit is stacked on PR #27, and CRC-enriched
Lua partial snapshots are supplied by the independently stacked
PR #25 (which itself follows PR #24). Review those dependencies before
treating the CRC report as available in a deployed toolset. Do not
merge this PR while those prerequisites are unreviewed.

**Crucial boundary:** CRC32 is not a cryptographic signature and does
not prove *originality*, VBlank age, or temporal alignment. Even when
all 64 CPS-A/B words agree and both CRC checks pass, the report
continues to set `frame_sync_verified: false` and
`pixel_parity_eligible: false`. No game assets, original frames or
internal CPS-1 buffers are checked into GitHub.

**Local reproducible validation:** The exact audit source and its
two test modules were checked against their GitHub blob SHA values
and executed locally in an isolated Python test tree together with the
Stage 42 probe decoder. All **17/17** tests passed, including same-size
register corruption, file swapping, null/invalid manifest CRCs, and
the strict CLI flag. Full GitHub Actions test execution and live MAME
C++/Lua synchronization remain unverified (issue #20).

## Stage 56 — opt-in latch callback event counter (not hardware VBlank)

The MAME 0.289 Git blob was independently re-checked against the exact
upstream `mamedev/mame` tag `mame0289`: upstream
`src/mame/capcom/cps1_v.cpp` still has SHA-1
`c1b5e3867824d0d1877b981142db7741346d2c55`.
Its `cps1_objram_latch(int state)` copies the mutable OBJ into
`m_buffered_obj` on a true `state` call.

The source generator now adds a diagnostic-only
`std::atomic<unsigned long long>` **emulator callback counter** after
the original memcpy statement (guarded to `dino`), and records a
single snapshot of its value at the beginning of
`screen_update_cps1`. Alongside the existing 2048-byte OBJ and
128-byte render-register files it writes a third small text sidecar:

```text
frame-00000900.obj-latch-count.txt
CPS1_DINO_LATCH_V1 401
```

The example number `401` is **illustrative only**, not a real MAME
measurement. The probe checks for pre-existing output names of all
three files before writing any new ones; the source is still generated
only into a separate opt-in copy and never overwrites its input.

The multi-frame CLI defaults to the original behavior, labeling
`obj_latch_count_evidence.status=NOT_REQUESTED` when no optional
counter trace was requested. With an actual private instrumented MAME
run that emitted all sidecars, the user may opt in:

```sh
python3 tools/mame_obj_sequence_alignment.py cps1-captures \
  --latch-count-evidence --out local_outputs/latch-audit.json
```

This option **requires every** corresponding
`frame-XXXXXXXX.obj-latch-count.txt` file. The parser enforces a
bounded 64-byte line, version tag, canonical unsigned decimal uint64
and monotone counts without gaps. It rejects missing, malformed,
oversized, reset/decreasing or overflowed values. It reports only
nominal frame labels, per-sample counts, differences between samples,
intervals with zero or multiple recorded callbacks, and intervals
where sampled OBJ bytes changed despite zero observed callback count
difference. The probe never publishes original OBJ bytes in JSON.

**Critical scope:** A `state == true` emulator latch **callback**
is not an independently observed physical VBlank signal. A counter
difference over `--frame-step=2` says only that callbacks happened
between two video-update samples; it cannot identify the timing of
the displayed frame or whether a particular buffered OBJ came from
the preceding original arcade VBlank. Counts are process-local and
may reset if MAME restarts. No new artifact proves original dino
pixel parity or native Switch gameplay.

The original-source probe is verified by exact anchor/SHA matching
and ROM-free unit tests, **not** by compiling a private modified MAME
0.289 executable or reading authentic original-game captures. All
new results remain `diagnostic_only:true`,
`obj_latch_age_verified:false`, `frame_sync_verified:false`,
`pixel_parity_eligible:false`.

## Stage 57 — V2 OBJ byte fingerprint binding (synthetic/opt-in)

Stage 56 wrote a latch callback count beside the 2048-byte OBJ dump,
but those two local files were not explicitly bound to the **same**
byte observation. A correctly sized OBJ sidecar accidentally swapped
between captures could be combined with the wrong latch count without
the old parser noticing.

The experimental generator now writes `CPS1_DINO_LATCH_V2`:

```text
CPS1_DINO_LATCH_V2 401 28c31cf8df2ec325
```

The displayed value is an **illustrative** 64-bit FNV-1a fingerprint
of 2048 zero bytes (not a real game capture). The generator reads the
callback count at the start of the video-update probe and computes
**FNV-1a 64** from all 1,024 buffered OBJ words in serialized
**big-endian** order. It then independently dumps those words and
stores the observed count plus the 16-character lowercase checksum in
the small private `frame-XXXXXXXX.obj-latch-count.txt` file. All
three probe outputs still refuse to overwrite existing files.

With `--latch-count-evidence`, the analysis CLI loads the existing
2048-byte OBJ probes in memory, recalculates FNV-1a and requires an
exact fingerprint match for **every V2 sample**. Partial, mismatched,
reset, overflowed, duplicate/malformed or mixed V1/V2 sidecars are
rejected *before* publishing an audit JSON. FNV uses a 64-bit modulo
counter and standard offset basis `14695981039346656037` and multiplier
`1099511628211`. This is a fast accidental-file-integrity check,
**not a cryptographic authenticator**.

The legacy `CPS1_DINO_LATCH_V1 <count>` format remains readable. Its
output explicitly reports `sidecar_format_version:1`,
`obj_byte_fingerprint_binding:"LEGACY_V1_NOT_BOUND"` and a verified
count of zero. All-V2 reports indicate
`obj_byte_fingerprint_binding:"FNV1A64_ALL_SAMPLES_MATCHED"`
and the number of locally matched sidecar files. A V2 report without
the original OBJ sidecars is refused instead of presenting an
unsupported binding claim.

14 new ROM-free regression methods test numeric vectors, endian byte
ordering, mismatched or swapped same-sized OBJ data, missing input,
corrupted format, V1 backward compatibility, V1/V2 series mixing,
counter resets, full synthetic CLI operation, and fail-closed JSON
behavior; one extra existing source-generator test verifies FNV
constants, byte order and placement before writing the OBJ file.

**What this does not establish:** FNV-1a is not collision-resistant,
and two files produced by the *same* instrumented MAME process are
not independent evidence of arcade hardware VBlank timing, original
raster synchronization or MAME authenticity. An emulator build with
the instrumented original MAME 0.289 source has still not been compiled
or executed on original dino gameplay as part of this stage. Outputs
remain `diagnostic_only:true`, `obj_latch_age_verified:false`,
`frame_sync_verified:false`, and `pixel_parity_eligible:false`.

## Stage 58 — single OBJ snapshot and executable generated-C++ smoke test

Stage 57's V2 C++ source generator computed an OBJ FNV-1a 64
fingerprint from `m_buffered_obj[index]` and then **re-read that same
mutable buffer** when serializing the 2,048-byte sidecar. If the
buffer changed between those two loops, the V2 digest could disagree
with the emitted file even though neither file had been substituted.

The video-update instrumentation now copies the **1,024 16-bit OBJ
words exactly once** into a private local 2-KiB stack array,
`observed_obj_words[0x400]`. Its FNV-1a hash uses these sampled
words in big-endian order and the file writer emits bytes from **the
same local array**, never re-reading mutable `m_buffered_obj` for
serialization. This guarantees consistency between the two
representations of that captured local snapshot; it does **not**
prove the buffer was latched at a particular VBlank or establish
inter-thread atomicity at the point of sampling.

Added `tests/test_mame_obj_probe_cpp_smoke.py`, which invokes
`instrument()` on a carefully bounded **ROM-free mock** of MAME's
`cps_state`, compiles the **actual generated C++** with
`g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -pthread`,
and executes the resulting mock executable. It checks:

- Four actual on-disk 2,048-byte OBJ and 128-byte CPS-register probe
  files plus four textual latch sidecars.
- Counter deltas and unchanged-OBJ behavior across fake latch calls.
- Real C++ V2 FNV values, independently checked against Python's
  `obj_fnv1a64()` applied to the emitted bytes.
- Presence guards preventing overwrite when one of three frame
  sidecars already exists, and the `dino`-only scope.
- The generated probe uses only **one** `m_buffered_obj[index]`
  read per slot and emits the saved snapshot, not a second read.

**Verification boundary:** This is a real C++ compilation and
execution of the injected callback **inside fake MAME class stubs**.
It is more meaningful than string-only instrumentation tests, but
it is **not** compilation of upstream MAME 0.289 itself and it
does not use actual game ROMs, game VBlank, original pixels, or
physical Nintendo Switch hardware. All alignment and parity flags
remain false, and original capture data stays outside GitHub.

## Stage 59 — verified original MAME source injection in hosted CI

Mock-compiled generated C++ proved the probe can compile in a small
`cps_state` fixture, but that alone did not exercise the **complete
original** `src/mame/capcom/cps1_v.cpp` from MAME version 0.289.

The `CPS-1 Python tools` GitHub Actions workflow now fetches a
**temporary, unmodified upstream copy** directly from
`mamedev/mame` tag `mame0289` and runs two separate checks:

1. Execute `tools/mame_obj_source_probe.py`, which requires the
   **exact expected upstream Git blob SHA-1**
   `c1b5e3867824d0d1877b981142db7741346d2c55`, then writes a
   new generated C++ copy without overwriting the original.
2. Execute `tools/mame_obj_real_source_audit.py`, independently
   checking three **exactly scoped** modifications: adding
   includes/counter storage, observing actual
   `cps1_objram_latch` after its original memcpy, and sampling OBJ
   after `find_last_sprite()` inside the video update. It removes
   the expected insertions **in memory** and demands
   **byte-for-byte restoration** of the original 0.289 source.
   Unrecognized changes, wrong source versions, renamed/missing
   anchors or mismatched probe payloads fail the job.

The CLI emits only source and generated SHA-256 metadata, the fixed
Git blob, and conservative verification flags. Upstream source,
modified MAME C++, private game captures and ROM bytes are all kept
out of the repository and artifacts. Temporary sources are erased
using a shell exit trap. Nine additional ROM-free Python regression
methods test source restoration, mutation and substitution failure,
wrong upstream version, malformed UTF-8 and command behavior.

**Verification boundary:** This automated gate confirms that our
generator applies **only the reviewed insertions to genuine upstream
MAME 0.289 video source**. The separate Stage 58 tests compile and
execute the generated insertion against mock MAME classes. Neither
step is a full real MAME build using its entire header/dependency tree,
and neither starts an original-game emulator or verifies its VBlank
chronology or pixels. Upstream fetch/network errors will fail the CI
step and must not be misrepresented as game-code regressions.

MAME developer documentation describes a driver-scoped build using
`make SUBTARGET=<name> SOURCES=src/mame/capcom/cps1.cpp REGENIE=1`
with MAME's required compiler, SDL and development headers. Such a
full-tree compile/run remains a **separate future acceptance
requirement**, not a result of this stage. No ROMs are included in
any build recipe.


## Stage 60 — experimental full-tree MAME 0.289 CPS-1 build

The prior source gate proved exact upstream source modifications, but
deliberately did **not compile actual upstream MAME**. A separate,
opt-in GitHub workflow at .github/workflows/mame0289-cps1-build.yml now
attempts that stronger test on a GitHub-hosted Ubuntu runner **without ROMs**.

The workflow uses the official upstream tag mame0289, **pinned to**
commit f34f02505e32c1993c6a782b6814232cbfc74e36. It fetches a
temporary full checkout under the runner temp directory, checks the
commit ID, runs the existing source generator and independent
byte-restoration audit, then copies the generated cps1_v.cpp into
**only that disposable upstream checkout**.

MAME's documented Debian/Ubuntu dependencies are installed; the
actual source-target build command is:

    make -j2 SUBTARGET=dino SOURCES=src/mame/capcom/cps1.cpp REGENIE=1 NOWERROR=1 SYMBOLS=0 OPTIMIZE=0 TOOLS=0 TESTS=0

This compiles the complete dependencies needed for a CPS-1-only
emulator target (not just a mock cps_state or isolated stub). If the
build succeeds, a subsequent **ROM-free** -listxml dino command
tests driver metadata availability. No game ROMs, commercial sprite
assets, MAME binary, or generated MAME C++ are uploaded.

The full-tree job is resource-intensive and intentionally runs only
on a change to its own workflow path or on **manual GitHub Actions
dispatch**; it is not a required every-push/PR job. A failed compile
or runner timeout must be reported as such and is **not** equivalent
to a successful MAME build. Changing this workflow can retrigger
the expensive job; do not add it as a broad pull-request check.

A separate five-test Python module checks the recipe's pinned upstream
version, exact source-target build, opt-in nature and absence of
source/binary upload. These tests are structural guardrails, **not
evidence of successful compilation**. CI job outcomes must be
validated against the specific run and commit before any success
claim.

Even if the full emulator builds and can print driver XML without
ROMs, it still does not establish runtime authenticity of dino
captures, real VBlank latch age, pixel-perfect images or physical
Nintendo Switch gameplay. The previously approved cover and game
assets remain separate and untouched.

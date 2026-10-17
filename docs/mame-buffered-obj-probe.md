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

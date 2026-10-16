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

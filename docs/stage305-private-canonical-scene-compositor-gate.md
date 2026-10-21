# Stage305 — gated native/Python CPS-1 scene composition with original graphics

The Stage304 bridge lets the existing portable C/Python CPS-1 decoder
work directly with the user's canonical, source-SHA-verified private
`dino.zip`, rather than only legacy ROM filenames.
Stage304's private test compared **2,002 original graphics cells** (563,200
indexed pixels) with zero C/Python mismatches and confirmed complete
4,194,304-byte graphics equivalence between legacy and canonical archives.

Stage305 builds the next **source-data + synthetic-state** control. It
does not invent evidence of live MAME gameplay.

## Private local validation command

Use the complete authorized `dino.zip` prepared by Stage299, with the
original 16 ROM members outside any public GitHub tree:

~~~sh
python tools/cps1_private_canonical_scene_gate_305.py \
  --rom /private/roms/dino.zip \
  --out /private/audits/stage305-scene-report.json
~~~

This runs `tools/cps1_private_scene_compositor_parity.py`, which
compiles the **actual portable C scene compositor** from
`source/cps1_scene.c` plus `source/cps1_tile.c`, renders 14
fully specified test cases, and independently renders them in Python.

The gate first requires **all sixteen** original ROM contents to match
both the public source CRC32 and full SHA-1 for historical MAME 0.106,
including original non-graphics ROMs. It does not permit a partial
graphics-only archive or a mixture of old/new ROM aliases.

## Exact synthetic compositor contract

The input tiles come from the original user-owned ROM. The rest of
the frame state is **intentionally invented**:

- Scroll1, Scroll2 and Scroll3 tilemap codes/attributes and scroll positions;
- palette RAM and backdrop color;
- priority mask groups, pen-15 transparency and layer order;
- synthetic sprite/OBJ lists and layer control registers.

Both implementations render 384×224 RGBA frames, checked for exact
equality across **14 scenarios**, or **1,204,224 compared RGBA pixels**.

The ten required controlled differential checks include priority mask
changes, selective priority groups, transparent-pen invariance and
opaque-palette remapping. A positive result requires all expected
changes to be nonzero and all required invariances to remain zero.
Every comparison must hold synthetic scroll/OBJ/palette inputs fixed
except the **single deliberate** control change under test.

The Stage305 **aggregate gate** additionally rejects a forged or
incomplete upstream success, including missing or reordered scenarios,
incorrect pixel counts, any per-case mismatch, absent differential
fields, Boolean values masquerading as numeric evidence, incorrect
frame dimensions and any claim of real gameplay/console authenticity.

It returns one of:

- `PRIVATE_CANONICAL_DINO_SYNTHETIC_SCENE_C_PY_PARITY_PASSED`
- `BLOCKED_PRIVATE_CANONICAL_DINO_ORIGINAL_ROM_HASH_GATE`
- `BLOCKED_PRIVATE_DINO_SYNTHETIC_SCENE_PARITY_COVERAGE`
- `BLOCKED_PRIVATE_DINO_SYNTHETIC_SCENE_SETUP`

An optional private JSON receipt contains only bounded counters and
fixed Boolean/status fields. It excludes ROM bytes, decoded pixels,
original game frames, private file paths, source hashes and game input.

## Strictly ROM-free public tests

~~~sh
python -m unittest discover -s tests -p 'test_cps1_private_canonical_scene_gate_305.py' -v
~~~

Fifteen synthetic tests exercise successful *artificial* scene
report handling and deliberately corrupted reports, including one
pixel mismatch, missing or reordered control scenarios, wrong
priority/palette changes, missing origin hash evidence and fake
original-game or hardware Switch claims. None uses copyrighted game
assets or actual captured MAME frames.

## Evidence boundary and next step

A Stage305 success is **original static graphics data** composed with
**synthetic runtime state**, verified by the Switch project's portable
C code and independent Python reference. It does NOT prove:

- any original Cadillacs and Dinosaurs program was executed by MAME;
- a real game's palette RAM, tilemap VRAM, object buffer or sprite
  priority state was sampled;
- original `dino.inp` / `dino.wlf` replay;
- input/video synchronization or sound parity; or
- rendering on an actual Nintendo Switch console.

The next evidence gate remains a private, compatible historical
MAME 0.106 `-verifyroms dino` and gameplay frame capture. Neither
can be substituted by a ROM checksum check or synthetic compositor.

**Original ROM/INP/WLF, private captures and reconstructed original
game images must not be uploaded to public GitHub CI, PR artifacts
or releases.**

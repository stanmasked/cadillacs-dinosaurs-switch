# Stage 25 — Verify original dino ROM readiness before MAME

The latest stage-24 capture-to-Switch pipeline is blocked on live MAME
execution, not on a lack of an interface for transferring frame data.
We now have a separate, **entirely offline ROM set preflight** for the
original Capcom CPS-1 `dino` set (World 930201).

## Core game set vs. archival programmable logic

`tools/mame_rom_readiness.py` checks a private user's ZIP without
extracting, uploading or publishing any game data. Every member is
decompressed internally to verify the CRC stored in the ZIP header, and
the script checks expected file lengths and public MAME CRC metadata.

The tool distinguishes:

- **16 emulation-essential parent-set ROM members:** three Motorola 68000
  program ROMs, eight CPS-1 graphics ROMs, four QSound samples and one
  QSound Z80 program ROM.
- **12 separate archival programmable-logic (PLD) dumps:** important
  preservation data but not the same byte streams as the CPU, graphics
  and audio ROMs. Their CRC differences are reported separately and do
  not automatically mean the *core* game bytes are damaged.
- **Separate QSound HLE device archive:** MAME's QSound HLE device
  references `dl-1425.bin`, exactly 8,192 bytes with
  CRC32 `d6cf5ef5` in
  [MAME qsoundhle.cpp](https://github.com/mamedev/mame/blob/master/src/devices/sound/qsoundhle.cpp).
  This file is not an expected member of `dino.zip`.
  A modern MAME setup may require `qsound_hle.zip` in its configured
  ROM/device search path.

The expected program, graphics and audio CRCs are from the public MAME
`ROM_START(dino)` definition and MAME ROM-set metadata. For versioned
differences, consult `mame -listxml dino` and `mame -verifyroms dino`
using your installed MAME version.

## Usage

```sh
python3 tools/mame_rom_readiness.py /private/dino.zip \
  --out /private/dino-preflight.json
```

When a separately licensed / user-provided QSound HLE device ROM is
available:

```sh
python3 tools/mame_rom_readiness.py /private/dino.zip \
  --qsound-hle /private/qsound_hle.zip \
  --out /private/dino-preflight-with-device.json
```

No device archive is downloaded or created by this project. The script
refuses to overwrite a report.

Exit codes: **0** both the core game and supplied device ROM pass
metadata checks; **1** at least one required input is absent, invalid
or was not provided for verification; **2** corrupt or unsafe ZIP,
I/O failure or existing output file. Exit 0 is **not proof of a live MAME
boot**.

## Local inspection of the user-provided dino.zip

The available original archive was read privately:

| Area | Expected members | Matching |
| --- | ---: | ---: |
| Main CPU / graphics / sound core | 16 | 16 |
| Archival PLD dumps | 12 | 11 |
| QSound HLE device | separately supplied | not supplied here |

One isolated PLD entry, `ioc1.ic1`, is **279 bytes, CRC32 0d182081**
in the local archive versus the published reference's **260 bytes,
CRC32 a399772d**. This is explicitly flagged as an *archival* warning,
not misreported as a corrupted 68000 program or invalid graphics data.

The original `dino.zip` passed full ZIP member decompression/CRC
verification, with no missing members from the 16 core files.

**Still not verified:** MAME executable installation or startup,
matching of every device/BIOS requirement for the exact installed MAME
version, gameplay, correct first-level state, original frame capture,
or actual Switch hardware testing. The QSound HLE reference is verified
from MAME's own source, but no separate device ZIP was present.

## No-ROM tests

```sh
python3 -m unittest tests.test_mame_rom_readiness -v
```

Ten deterministic synthetic tests cover expected metadata, exact/missing
CRC checks, separation of game and device, corrupted ZIP handling,
duplicate/path-traversing names, inflated-size bounds, and safe report
creation. Only tools, tests and public metadata are committed; game
ROM bytes are never checked into GitHub.

**Follow-up:** supply the separate QSound device file locally (if
required by installed MAME), audit with `-verifyroms`, run the optional
render-pass capture instrumentation, then transfer actual captured frames
through PR #11 to the existing native Switch v0.5 viewer.

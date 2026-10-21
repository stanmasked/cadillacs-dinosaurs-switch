# Stage302 — original dino ROM mapped into CPS-1 regions from actual MAME 0.106 source

## Purpose

The original authorized `dino.zip` and the code-only historical MAME
0.106 source bundle are now available together in a private session
workspace. An emulator execution of the Windows PE32 binary is still
blocked because Wine or another compatible Windows runtime is not
installed, and the runtime has no network access to install one.

Rather than asserting a nonexistent successful emulator boot, Stage302
performs **source-grounded memory reconstruction of the original ROMs**.
This goes beyond Stage299's checksum identity: it independently follows
the program's real CPU, graphics and audio load declarations.

## Verified private experiment

Parsed the exact `ROM_START( dino )` block from the historical source:
`mame0106/src/drivers/cps1.c`. For each of the 16 original
ROM members, revalidated both public source CRC32 and SHA-1 before mapping
the bytes. No ROM contents or region digests were printed or uploaded.

Applied the source's actual transforms:

- **68000 program**: three `ROM_LOAD16_WORD_SWAP` images, with
  bytes exchanged within each 16-bit word;
- **CPS-1 tiles/sprites**: eight `ROMX_LOAD` lanes, each loaded
  as 2-byte groups separated by six unfilled bytes in the destination;
- **Starfield**: `ROM_COPY` of the first 32 KiB of the populated
  GFX1 region into the dedicated GFX2 region;
- **QSound Z80**: `cd_q.rom` loaded first 32 KiB at zero, then
  `ROM_CONTINUE` maps its next 96 KiB to offset 64 KiB,
  leaving a deliberate 32-KiB unpopulated gap;
- **QSound sample ROMs**: four consecutive 512-KiB samples.

The private mapping yielded the following coverage counts:

| CPS-1 region | Allocated bytes | Bytes populated | Intentionally unpopulated |
|---|---:|---:|---:|
| 68000 CPU1 | 2,097,152 | 1,572,864 | 524,288 |
| GFX1 | 4,194,304 | 4,194,304 | 0 |
| GFX2 (copied stars) | 32,768 | 32,768 | 0 |
| Z80 CPU2 | 163,840 | 131,072 | 32,768 |
| SOUND1 | 2,097,152 | 2,097,152 | 0 |

**All eight graphics lanes populated their declared region without
unfilled bytes; the copied stars matched their GFX1 source.** The
original ROM archive was not modified. This is an actual check using
private original game bytes, not synthetic gameplay.

## Reproducible local validator (ROM stays private)

The new tool, `tools/mame0106_private_dino_rom_map_302.py`,
requires source-pinned MAME 0.106 code and the locally normalized
private original ROM. It validates the complete source directives,
canonical member names and all expected source checksum identities.

~~~bat
python tools\mame0106_private_dino_rom_map_302.py ^
  --rom C:\private\roms\dino.zip ^
  --mame-source C:\private\mame290-bundle\mame0106-source.zip ^
  --out C:\private\audits\stage302-cps1-map.json
~~~

The tool refuses unknown or modified ROM load macros, changed
source offsets, changed CRC/SHA1, overlapping region writes, out-of-
range groupword lanes, mismatched QSound continuation, copied graphics
from undefined bytes, missing image members and unexpected final
region coverage.

Its output is a fresh private JSON receipt with **only aggregate
region byte counts, boolean markers and an evidence-limited status**:

`PRIVATE_DINO_CPS1_REGION_LAYOUT_MATCHES_MAME0106_SOURCE_UNAUTHENTICATED`

No original game image, input recording, ROM bytes, mapped regions,
per-file private hashes or uncompressed data are included in the report.

## Public regression tests

~~~sh
python -m unittest discover -s tests -p 'test_mame0106_private_dino_rom_map_302.py' -v
~~~

Public CI uses only invented byte strings and **public** historical
ROM metadata. These tests cover 68000 word swap, 8-lane CPS-1
groupword interleave, QSound continuation, starfield copy, source
declaration matching, duplicate/overlapping writes and corrupt
layout rejection. The original private ROM is never sent to CI.

## Evidence boundaries

This stage is **original ROM data mapping**, **not** original game
execution. Its success does not establish:

- a running historical MAME `-verifyroms dino`;
- original Cadillacs and Dinosaurs boot, video frames or audio;
- authentic WolfMAME 0.106 anti-cheat/replay provenance;
- original user `dino.inp` or `dino.wlf` replay;
- original input-to-video causal synchronization; or
- a physical Nintendo Switch test or remake parity.

Those require executable/runtime access and the original private
input recordings. Keep every source asset and derived video outside
GitHub, PRs, CI and public artifacts.

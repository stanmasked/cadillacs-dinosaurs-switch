# CPS-1 dino graphics ROM region

Reference: MAME `dino` (World 930201). Eight graphics ROMs (each 0x80000 bytes) form a **0x400000-byte** graphics region.

Each bank interleaves four ROMs as 16-bit words in an 8-byte stride:

| Bank | Offset within bank | ROM |
|---|---|---|
| 0 | 0 | cd-1m.3a |
| 0 | 2 | cd-3m.5a |
| 0 | 4 | cd-2m.4a |
| 0 | 6 | cd-4m.6a |
| 1 (base 0x200000) | 0 | cd-5m.7a |
| 1 | 2 | cd-7m.9a |
| 1 | 4 | cd-6m.8a |
| 1 | 6 | cd-8m.10a |

Run `python3 tools/cps1_gfx.py /path/to/dino.zip` locally; output is metadata only.

Local verification against supplied World 930201 ZIP:
- Region length: **4,194,304 bytes**.
- Assembled region SHA-256: `68786de27105ccc64f28f66ad1025f2e6f521aa60ab35c489fb0baaaa8679de1`
- Three standalone graphics mapping unit tests: **PASS**.

This reconstructs the ROM region, not CPS-1 graphics decoding, sprite placement, palette selection, or a playable game. ROM data and extracted assets must not be committed.

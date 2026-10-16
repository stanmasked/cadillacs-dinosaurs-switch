# CPS-1 indexed tile decoder (World 930201)

## Verified source geometry

MAME defines four views of the same 0x400000-byte graphics region in `src/mame/capcom/cps1.cpp`:

| Layout | Size | Code stride | Code slots |
| --- | ---: | ---: | ---: |
| scroll1 half A | 8×8 | 64 bytes | 65536 |
| scroll1 half B | 8×8 | 64 bytes | 65536 |
| sprite / scroll2 | 16×16 | 128 bytes | 32768 |
| scroll3 | 32×32 | 512 bytes | 8192 |

These are addressable code slots, **not counts of unique assets**. CPS-1 B-board mapper rules determine which code ranges are actually valid for each layer. Both 8×8 views share the same 64-byte code with different x-offsets. Pixel depth is 4 bpp (indices 0–15); pen 15 is transparent in the diagnostic export.

The implemented pixel-plane bit offsets are 24, 16, 8, 0, using x offsets as specified by MAME. The 16×16/32×32 and both 8×8 layouts were checked using independent synthetic test vectors. They were also decoded from the provided parent ROM set, without publishing its contents.

## Local verification

```sh
python3 -m unittest discover -s tests -v
python3 tools/cps1_tiles.py /your/path/dino.zip --layout 16x16 --start 0 --count 128 --columns 16 --scale 2 --out local_outputs/tiles16.png
python3 tools/cps1_tiles.py /your/path/dino.zip --layout 32x32 --start 0 --count 64 --columns 8 --scale 2 --out local_outputs/tiles32.png
```

The PNG writer uses only Python standard libraries. **The PNG is a diagnostic indexed-pixel display in synthetic grayscale, not the original color palette.** Accurate color requires runtime CPS-1 palette RAM and tile/sprite attributes. Recovering palette assignment, tile-validity banking and on-screen assembly is a separate task.

For the user-supplied `dino.zip`, the assembled graphics region is 4,194,304 bytes and has SHA-256 `68786de27105ccc64f28f66ad1025f2e6f521aa60ab35c489fb0baaaa8679de1`.

## References

- [MAME CPS-1 driver, source layout definitions](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1.cpp)
- [MAME CPS-1 video mapper notes](https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp)

No ROMs, assembled ROM regions or extracted original artwork are committed to this repository.

# Stage 273 — fail-closed PNG scanline integrity (ROM-free)

Strengthen the Stage272 private screenshot receipt validator. A valid PNG **signature**, correctly checksummed PNG **chunks**, and a valid **zlib stream** do not on their own establish a real decodable image: IHDR may disagree with the decompressed pixel layout, an invalid PNG filter can precede a row, or an indexed image may omit its palette.

New `png_integrity` validation (for 8-bit noninterlaced PNGs only):

1. Require IHDR first and IEND last; reject duplicate IHDR, unsupported critical chunks, misplaced or missing palettes for indexed PNGs, and noncontiguous IDAT.
2. Bound dimensions and the full image decompressed size to **64 MiB**, and limit DEFLATE expansion before accumulating bytes.
3. Require *exactly* `height × (1 + width × bytes_per_pixel)` decompressed bytes for each accepted PNG color type.
4. Require a valid PNG filter byte `0..4` at the start of every scanline.
5. Reject trailing deflate input, incomplete streams, incorrect chunk CRCs, or any extra bytes after IEND.
6. Continue recording SHA-256 over the exact file bytes; only `scanline_size_and_filters_verified` is added to the output.

The 12 synthetic tests cover valid RGB/RGBA, indexed PNGs with/without palette, invalid filters and decompressed size, a noncontiguous IDAT pair, unknown critical chunks, ancillary metadata and trailing compressed data.

```sh
python3 -m unittest discover -s tests -p 'test_wolfmame0106_png_scanline_proofs.py' -v
```

**Limits:** This does not fully perform per-pixel PNG color reconstruction, prove emulator provenance, establish original INP frame alignment, reveal game assets, or assert physical Nintendo Switch parity. The original `dino.inp`, `dino.wlf`, ROMs and captured game pixels stay local and are not tracked in GitHub.

This branch is stacked on Draft PR #80 and does not modify the upstream tested commit. All tracked examples are synthetic.

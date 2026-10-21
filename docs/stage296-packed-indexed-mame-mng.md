# Stage296 — support packed indexed MAME PNG frames in private MNG audit

## Concrete failure in Stage295

The historical MAME 0.106 **really executed** an artificial Minivader
8-KiB Z80 program, generated a synthetic INP recording, and replayed it in
the same custom historical MAME build. Windows CI run:

https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39667543711

The replay process returned zero, created MNG and 24 ordered numeric read
counter rows for synthetic callback indices 10 through 33. The MNG
auditor still rejected the actual video:

`BLOCKED_SYNTHETIC_MNG_DECODING`.

Upstream `mamedev/historic-mame` at tag `mame0106`, file
`src/png.c`, function `png_create_datastream`, is decisive:
when the frame bitmap has depth 16 and the emulated machine has no more
than 256 palette colors, the PNG writer chooses indexed color type 3.
It determines the PNG *bit depth* as follows:

| Number of indexed palette entries | PNG depth |
|---|---|
| 1–2 | 1-bit |
| 3–4 | 2-bit |
| 5–16 | 4-bit |
| 17–256 | 8-bit |

Our earlier Stage284 PNG audit accepted only depth 8 even for indexed
palettes. A real MAME Minivader frame can therefore contain a perfectly
valid packed **1-bit indexed PNG** and still be rejected as unsupported.
This is a format-support gap in our auditor, not proof of a corrupted
MAME recording.

## Implementation

The shared PNG structural verifier now accepts **1/2/4/8-bit indexed**
type-3 PNG, while non-indexed PNG modes remain constrained to supported
8-bit depth. It uses the correct number of bytes per row:

    packed_index_row_bytes = ceil(width * bit_depth / 8)

This prevents both false rejects and excessive/short decompressed
scanlines. The optional palette has to fit the selected bit depth,
chunk CRCs are still validated, zlib output is still bounded, and PNG
must have exactly one IEND and no trailing bytes.

The visual decoder now reverses each PNG scanline filter **in bytes**,
with predictor distance one for packed 1/2/4-bit palette data.
Then, for each actual pixel, it extracts its index most-significant
bit first using the indexed bit depth, maps only actual width pixels
to the existing PLTE values, and ignores row padding bits.

Any index outside the palette remains a hard error. Unexpected color
types, unsupported modes, bad palettes or malformed compressed data
remain rejected. No game image or original asset was needed to add
this support.

## ROM-free regression tests

`tests/test_mame0106_packed_palette_mng_296.py` covers invented
1-, 2-, 4-, 8-bit indexed PNGs, all five PNG row-filter modes, odd
image width and trailing padding bits, exact RGBA reconstruction,
invalid palette size and pixel indices, corrupted image data,
and multi-frame packed-index MNG including the 24-frame Stage295
synthetic capture shape.

Windows MAME CI on the Stage296 branch is explicitly enabled to repeat
the same *real MAME* synthetic Minivader record/playback and re-audit
the produced MNG with the new decoder. No user-provided game files,
original ROM, original INP/WLF, sprite images or real gameplay are
used or published.

## Outstanding evidence

Even if the synthetic 24-frame MNG now passes:

- The capture concerns **artificial Minivader**, not original dino.
- The instrumentation checks only successful input-port reads; it does
  not independently prove causal INP-to-video frame alignment.
- MAME source pins and unsigned manifests are not independent proof of
  WolfMAME binary provenance.
- The Nintendo Switch native bootstrap is not a physical Switch
  comparison against actual Cadillacs and Dinosaurs gameplay.

The next original-game parity gate remains a **local-only** authorized
replay of the user's original INP/WLF and ROM, keeping all content and
derived MNGs out of public GitHub.

# Stage306 — exhaustive, real original CPS-1 tile parity

## Local original ROM experiment: completed

Using the authorized, private 16-ROM canonical `dino.zip` from Stage299,
assembled the full 4,194,304-byte CPS-1 GFX region. Reused the real
portable C tile decoder from our Nintendo Switch project's
`source/cps1_tile.c`, previously compiled locally as a code-only
shared library, and implemented an independent Python 4-bit-plane
reference. No original ROM bytes, decoded tiles, screenshots or
per-file private checksums were written to public GitHub.

Unlike Stage304's 2,002 sampled graphics cells, this private experiment
examined **every legal tile code** at each supported size:

| Original CPS-1 tile mode | Exhaustive tile decodes | Compared 4-bit pixel indices | C↔Python tile mismatches |
|---|---:|---:|---:|
| 8×8 (both halves per code) | 131,072 | 8,388,608 | 0 |
| 16×16 | 32,768 | 8,388,608 | 0 |
| 32×32 | 8,192 | 8,388,608 | 0 |
| **Total** | **172,032** | **25,165,824** | **0** |

Both 8×8 halves were enumerated separately for every 64-byte
tile code: selecting index 0 vs index 32. All **sixteen pen values
0–15** appeared in each tile size. There were no failed native decode
calls or malformed tile results.

This checks exhaustive **static original ROM graphics encoding**.
It does not establish actual in-game tilemap indices, sprite animation,
palette, QSound audio, original MAME video or Switch framebuffer parity.

## Private local reproducer

The new tool `tools/cps1_private_exhaustive_tiles_306.py` is a
reproducible, self-contained reference comparison for the original
game owned by the user. It:

1. Rejects nonregular, unsafe, symlinked or public-repo archive paths.
2. Verifies **all 16 original source ROMs**, including CPU and audio,
   against historical MAME 0.106 CRC32 and SHA-1.
3. Builds the 4-MiB GFX region with the Stage304 canonical lane adapter.
4. Compiles the **actual** `source/cps1_tile.c` through local GCC into
   an ephemeral, code-only shared library.
5. Calls the C decoder for every tile and compares all pixels against
   independently expanded 4-plane Python reference values.
6. Requires zero wrong tiles, zero C failures, correct format totals,
   and all sixteen 4-bit indices present in **each** size category.
7. Prints only an aggregate fixed status label. Writes an optional
   exclusive 0600 **private report** containing numerical counts and
   explicit *false* flags for original gameplay/physical Switch tests.

Usage from the project checkout with GCC installed:

~~~sh
python tools/cps1_private_exhaustive_tiles_306.py \
  --rom /private/roms/dino.zip \
  --out /private/audits/stage306-exhaustive.json
~~~

The report must remain outside the public GitHub repository. No ROM
data, tile arrays, raw pixels, personal paths, SHA hashes or extracted
graphics are saved as artifacts.

## ROM-free regressions

~~~sh
python -m unittest discover -s tests \
  -p 'test_cps1_private_exhaustive_tiles_306.py' -v
~~~

Fourteen tests build the actual portable C decoder using *invented*
512-byte GFX patterns. They cover complete traversal of 8/16/32
modes and both 8×8 halves, exact C/Python equality, one deliberately
corrupted reference pixel, invalid reference output, malformed tile
indices, all-zero degenerate graphics refusal, unsafe symlinks, early
ROM hash preflight gating, and sanitized CLI failure.

The public test fixture is not a game ROM and uses no original graphics,
names or input recordings.

## Limits and next gate

This exhaustive private original-ROM parity is **stronger source
encoding evidence** than a sample, but it is not a reconstructed or
captured authentic MAME gameplay frame. Original VRAM, priority register
state, palette RAM, audio, player inputs and VBlank timing remain
unobserved in a live original game session.

Stage305 adds a separate *synthetic-state* C/Python scene compositor
gate, but only an actual private MAME 0.106 `-verifyroms dino` run,
video capture, and a source-authenticated VRAM/palette snapshot can
establish runtime frame parity. No original game content is uploaded
to GitHub Actions, public branches or downloadable artifacts.

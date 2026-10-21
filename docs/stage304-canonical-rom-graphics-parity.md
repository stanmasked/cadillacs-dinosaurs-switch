# Stage304 — original dino CPS-1 graphics with canonical ROM filenames

## Concrete integration failure and fix

The user's original private `Cadillac Dinosaur.zip` has eight graphics ROMs
using older CPS-1 names such as `cd-1m.3a`. Stage299
produced a verified private `dino.zip` with **16 canonical MAME
0.106 ROM filenames**, including graphics lanes such as
`cd_gfx01.rom`. The existing native/Python graphics parity
tool (`tools/cps1_private_native_tile_parity.py`) only knew the
older names. The correct, SHA-verified Stage299 archive was therefore
not directly usable by the established private tile tests.

The reader now accepts either **one complete legacy graphics lane
set** or the **complete canonical 16-member source ROM set**:

- Canonical input requires the exact Stage299 original ROM manifest:
  all 16 filename identities, sizes, public source CRC32 values, and
  full public source SHA-1 checksums pass before graphics assembly.
- The eight canonical graphics lanes map to the existing historical
  lane offsets, preserving each 2-byte/8-stride CPS-1 interleave.
- Mixed legacy + canonical archives are rejected as ambiguous.
- A canonical archive with an altered ROM (even a sound/program ROM)
  is rejected before tile decoding.
- Legacy input remains backward-compatible with existing owned-ROM
  usage; the reader still requires all eight correctly sized lanes.
- The local report never exposes ROM bytes, paths, pixel data or
  private file fingerprints.

## Independent local real-ROM graphics result

This stage also performed a **private, real original-game data
experiment** (outside public GitHub), using original `dino.zip`
and the 16 public hashes/sizes in the actual compiled MAME 0.106
`dino-driver.xml` catalog.

A four-megabyte graphics region was assembled from the eight actual
canonical original graphics lanes. Two independent decoders — one
Python reference and one separately compiled, original-ROM-free C
implementation — reconstructed four-bit palette-index pixels from
deterministic sampled tile addresses:

| CPS-1 tile layout | Compared tiles | Compared pen indices | Tile mismatches |
|---|---:|---:|---:|
| 8×8 (left + right halves) | 1,032 | 66,048 | 0 |
| 16×16 | 646 | 165,376 | 0 |
| 32×32 | 324 | 331,776 | 0 |
| **Total** | **2,002** | **563,200** | **0** |

**All sixteen possible 4-bit pen values** appeared in each size group.
The private original ROM was neither modified nor copied to GitHub;
only the aggregate counts are shared. This independent C exercise is
separate from GitHub's build of the actual Nintendo Switch rendering
code and **cannot establish original MAME game frames**.

The established parity tools can now consume the same canonical
original archive:

~~~sh
python tools/cps1_private_native_tile_parity.py /private/roms/dino.zip
python tools/cps1_private_multisize_tile_parity.py /private/roms/dino.zip
python tools/cps1_private_scene_compositor_parity.py /private/roms/dino.zip
~~~

Do not run these tools with original ROM in public GitHub Actions.
The compositor still uses synthetic scroll, object and palette state,
even though tile graphics originate from the private original ROM.

## ROM-free CI tests

~~~sh
python -m unittest discover -s tests -p 'test_cps1_private_canonical_graphics_304.py' -v
~~~

Twelve new tests use **invented** 16-member ROM ZIPs with independently
generated synthetic SHA-1/CRC32 reference metadata, exactly eight
512-KiB original-shaped graphics lanes, and harmless dummy program/
sound bytes. They verify:

- correct original legacy-to-canonical eight-lane order;
- full original-set hash check before graphics decode;
- identical graphics region from equivalent old/canonical aliases;
- rejection of one changed gfx byte, **or one changed unrelated ROM
  byte**, extra and missing files, duplicate names and mixed aliases;
- symlink refusal and continued support for the legacy archive.

## Critical evidence limits

Stage304 establishes consistency of real original CPS-1 **static
graphics encoding**, not runtime game execution.

No actual Windows MAME 0.106 `-verifyroms dino` run, boot video,
original `dino.inp` / `dino.wlf` replay or actual CPS-1
palette/scroll/priority data has been confirmed. A physical Nintendo
Switch rendering comparison is likewise outstanding. These still
require compatible private MAME execution and source input recordings.

The user's ROM and any original images or input recordings remain
outside the public repository and its artifacts.

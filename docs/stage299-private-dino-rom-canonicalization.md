# Stage299 — verify and privately normalize original dino ZIP

## Verified original ROM availability

The user's existing Google Drive folder for Cadillacs and Dinosaurs
contains `Cadillac Dinosaur.zip` (a privately fetched, non-public archive).
In the private execution workspace we inspected its ZIP catalog and
**verified all sixteen required dino ROM payloads against both the public
CRC32 and SHA-1 hashes in the source-pinned MAME 0.106
`src/drivers/cps1.c:ROM_START(dino)`.**

The source archive includes twelve additional members. Some required
ROM payloads use filenames different from the canonical MAME loader
names, even though their underlying content digests match. Passing
hashes proves those sixteen bytes match the historical public game-ROM
checksums, **not** that the game has booted in MAME or that the WolfMAME
original input replay works.

Do not upload any original ROM, original INP/WLF, derived game frames or
original audio to GitHub, its public Actions artifacts or PR attachments.

## Local-only private canonicalizer

The new tool `tools/mame0106_private_dino_rom_canonicalize_299.py`
validates the existing archive and creates a fresh, private
`dino.zip` with the sixteen **canonical MAME 0.106 ROM filenames**,
matched by **size, CRC32 and full SHA-1** against the historical
source manifest. The original ROM payload bytes are not changed.

Private inspection only:

~~~bat
python tools\mame0106_private_dino_rom_canonicalize_299.py ^
  --source C:\private\original\Cadillac Dinosaur.zip ^
  --report C:\private\audits\stage299-rom-verification.json
~~~

Create a new output file within a **private folder outside the Git
repository**:

~~~bat
python tools\mame0106_private_dino_rom_canonicalize_299.py ^
  --source C:\private\original\Cadillac Dinosaur.zip ^
  --output C:\private\roms\dino.zip ^
  --report C:\private\audits\stage299-rom-normalized.json
~~~

The output archive contains **exactly sixteen** matching canonical MAME
ROMs. Other original-archive members are ignored (not copied) and the
private ZIP is created exclusively with restrictive permissions; it
cannot overwrite an existing file.

The tool rejects path traversal, symlinked sources/outputs, duplicate
archive names, duplicate matching ROM payloads, missing files,
incorrect sizes, CRC/SHA1 inconsistencies, overly large or
excessively numerous ZIP members, and any output path inside the public
repository. Hash comparisons finish before any output file is created.

It prints only conservative status labels. Private JSON receipts contain
aggregate counts and boolean markers but **no original ROM bytes,
private file paths, per-file SHA-1 digests, original filenames,
screenshots or game input values**.

The output archive is meant for the next **private local** experiment,
not as a downloadable artifact, project attachment, GitHub Actions
artifact or release.

## Tests (strictly synthetic)

~~~sh
python -m unittest discover -s tests -p 'test_mame0106_private_dino_rom_canonicalize_299.py' -v
~~~

The public tests generate **invented** tiny ROM byte strings with their
own temporary checksum manifest, not original dino data. They exercise
checksum identity despite filename mismatches, exclusive private ZIP
creation, missing/corrupted/duplicate/unsafe members, symlinks,
uncompressed-size budgets and sanitized failure reports.

## What is still not proved

1. An actual MAME 0.106 `-verifyroms dino` run
   against the private normalized ZIP.
2. Authentic WolfMAME provenance and actual original
   `dino.inp` / `dino.wlf` playback; these recordings
   are still unavailable to this execution environment.
3. Causal alignment of original INP records and MAME's video callbacks,
   original game's graphics/audio parity, or real Switch gameplay.

None of those statements follows solely from CRC/SHA1 ROM identity.
Stage297's real Windows emulator test did pass 16 matching *dynamic*
frames and counters, but used only artificial Minivader, not dino.

The immediate next gate is a **private** historical emulator
`-verifyroms dino` check with the normalized ZIP and then
the local-only Stage298 activity-guided double capture once the original
INP/WLF and executable can be used in a compatible private runtime.

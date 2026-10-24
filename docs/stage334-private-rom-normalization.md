# Stage334 — private ROM filename normalization

## Finding

The user-provided original archive contains 28 board-labelled entries. The pinned MAME 0.106 dino driver manifest expects 16 canonical filenames. The private audit matched every expected entry uniquely by size, CRC-32, and SHA-1, but the source filenames differ from the names listed by the driver. This is a packaging-name mismatch, not evidence of corrupt ROM bytes.

A normalized private copy was created for investigation; the source archive was left unchanged. This does **not** mean MAME's own -verifyroms command has passed.

## Repeatable local tool

The ROM-free tool tools/wolfmame0106_private_rom_normalize.py reads:
- the original archive from a private local path;
- dino-driver.xml from the verified, source-pinned MAME 0.106 technical artifact.

It matches expected entries by all three integrity fields, rejects missing or ambiguous matches, refuses unsafe ZIP member names, limits archive/member sizes, and writes only the expected canonical entries to a new output archive. The output is created exclusively with private permissions outside the repository. The tool prints aggregate counts only; it never prints ROM filenames, paths, CRCs, SHA-1 values, or ROM bytes.

## Local procedure

First unpack the source-pinned MAME artifact into a private directory and verify its SHA256SUMS.txt plus the pinned mame0106.exe digest. Keep the original archive and the INP/WLF recording outside the checkout.

Create a private ROM output directory and run:

    python3 tools/wolfmame0106_private_rom_normalize.py \
      --source-zip "/private/cadillacs/original/Cadillac Dinosaur.zip" \
      --driver-xml "/private/cadillacs/mame/dino-driver.xml" \
      --out "/private/cadillacs/roms/dino.zip"

The output directory must already exist and must be outside the repository. The tool refuses to overwrite an existing output. The original archive is not altered.

Only after normalization passes, run the existing private read-only gate with --rom-dir pointing to /private/cadillacs/roms. A successful normalizer report is an integrity/packaging check only. Do not report MAME ROM verification or gameplay replay as successful until the real MAME -verifyroms dino command succeeds on a compatible private host.

## Validation and privacy

Seven synthetic tests cover canonical renaming, byte preservation, missing/ambiguous content, symlink rejection, traversal rejection, output overwrite refusal, and repository-output refusal. Tests use only artificial byte strings. No original ROM, INP/WLF, normalized archive, MNG, or CSV trace is included in GitHub or Actions.

The private source archive, normalized dino.zip, driver XML, capture, and trace remain outside the public repository. PR #139 remains Draft; main is unchanged.

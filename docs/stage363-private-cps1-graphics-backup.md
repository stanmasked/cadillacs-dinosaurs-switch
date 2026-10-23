# Stage363 — private CPS-1 GFX archive with tested recovery

This workflow independently advances original-graphics resource preparation
while a private Windows runtime for genuine historical MAME 0.106
`-verifyroms dino` remains unavailable. No gameplay execution is claimed.

Run the locally owned original ROM archive through
`python -m tools.cps1_private_graphics_backup --source-zip <private-original-zip> --source-sha256 <private-pinned-source-hash> --archive <new-private-gfx-backup.zip> --manifest <new-private-manifest.json>`
outside GitHub Actions. Both output paths must be new and outside the
public repository tree. The source and graphics archive remain owner-only.

The tool verifies the SHA-256 pin of the original archive, checks ZIP
inventory and CRC, requires eight correct 512-KiB CPS-1 GFX lanes,
assembles the 4-MiB ROM graphics region with the established
`cps1_gfx.assemble_gfx`, and proves every lane can be reconstructed
byte-for-byte from the assembled region. It creates two 64-tile
diagnostic PNG atlases (16×16 and 32×32, grayscale only).
No original palette or actual emulator gameplay frame is present.
Archives have stable ordering and timestamps, member SHA-256 in a
PRIVATE manifest, are read back in full, and cannot overwrite
an existing output.

Verification completed in a private local scratch workspace:
8/8 source GFX lanes round-trip, 4,194,304-byte assembled region;
two RGBA grayscale diagnostic atlases, each 256×256 pixels;
four ZIP members, CRC and SHA-256 verified.
Nine synthetic-only regression tests passed locally with
GITHUB_ACTIONS=true. The private archive and detailed manifest were
backed up to owner-only Google Drive and re-downloaded byte-for-byte.
The backup ZIP is 2,028,694 bytes. Its SHA-256:
857e36ab41b2026c43bddc2b20ecd953f871d7dafb3cb20cd6913da649cb2f3b.

The public commit contains ONLY this code, synthetic tests and
sanitized documentation. The original and transformed graphics,
private input recordings, original frames, detailed file-level hashes
and captures are excluded from GitHub, CI and public artifacts.

Real MAME 0.106 ROM verification, INP replay, gameplay video parity,
and Nintendo Switch physical hardware testing remain unverified.

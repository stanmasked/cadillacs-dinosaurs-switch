# Stage360 — checksum-identical historical MAME 0.106 ROM naming adapter

The owner-held original ROM ZIP uses newer ROM filenames than the historical
MAME 0.106 dino driver. A private offline audit against the SHA-256-pinned
historical MAME 0.106 -listxml matched all 16 required ROM payloads unambiguously
by uncompressed size, CRC32 and SHA-1. No payload bytes were edited; only ZIP
entry names were changed to match the old driver.

Public code-only adapter: tools/mame0106_private_rom_name_adapter.py
Synthetic-only regressions: tests/test_mame0106_private_rom_name_adapter.py
The private adapter validates externally pinned source and driver-XML SHA-256
before reading either input. It refuses duplicate, ambiguous, missing, corrupt,
oversized, encrypted or unsafe ZIP entries. Output is deterministic and
independently rechecked. Existing output paths cannot be overwritten.

The original source archive, old and new ROM names, raw input recordings,
the resulting adapted ROM ZIP, and full private file-level hash manifest
remain exclusively in the owner's private Google Drive archive, not GitHub.
The content-derived set was uploaded and downloaded back successfully;
private archive and manifest SHA-256 readbacks matched their local copies.
Neither original game ROM nor input recording is attached to this PR,
any GitHub Actions workflow, or any public artifact.

Counts: input ZIP 28 members; old MAME expected ROM payloads 16; exact
size/CRC32/SHA-1 matches 16/16. The adapted archive contains 16 members.
This is ROM-set naming readiness only. Actual historical MAME
-verifyroms, recorded dino.inp playback, gameplay capture and Switch
hardware execution are NOT established by this step.

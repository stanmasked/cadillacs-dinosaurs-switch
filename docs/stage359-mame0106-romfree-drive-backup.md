# Stage359 — durable ROM-free MAME 0.106 technical archive

Stage358 native Windows ROM-free preflight: run 40024646549, success.
SHA-256 verification: eight manifest entries; MAME -help, -showconfig and
-listxml all passed; original dino driver was present in 26,211,837 bytes of XML.
Python, Nintendo Switch bootstrap and both repository privacy gates passed.

The ROM-free MAME technical ZIP from run 39859311511 / artifact 12461451785
was copied to the project's owner-only Google Drive archive before the
temporary GitHub artifact's 2026-10-25 expiration. This ZIP contains no
original game ROM, INP/WLF, derived sprites, screenshots or private traces.

Pinned stored ZIP SHA-256:
5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a
Size: 41,450,235 bytes; 12 flat technical members; unpacked: 139,106,373 bytes.
The stored Google Drive copy was downloaded back and compared byte-for-byte
against the GitHub artifact. Both hashes matched.

Offline verification after restoring the ZIP from the private Drive:
  python tools/mame0106_romfree_archive_restore.py --archive /path/to/bundle.zip
Safe extraction into a NEW scratch directory, never overwriting:
  python tools/mame0106_romfree_archive_restore.py --archive /path/to/bundle.zip --extract-to /path/to/new-scratch-dir

Fail-closed checks: pinned outer SHA-256, exact 12-file inventory, no paths or
symlinks, extraction limits, eight signed technical manifest entries, MAME
executable SHA-256 and PE32-i386 header, pinned original source commit and
CRC-checked members. Tests use synthetic ZIPs only.

Google Drive remains the source for private originals, extracted graphics,
raw captures and traces. Public GitHub contains only code, synthetic tests,
technical hashes, and sanitized aggregate reports. Historical native MAME
ROM-free success does NOT demonstrate original dino.inp playback, ROM verify,
WolfMAME replay, or Switch hardware execution.

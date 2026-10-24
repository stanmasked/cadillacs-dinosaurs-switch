# Stage373 — file-identity and preflight-provenance hardening

Stage372 classified owner-only evidence correctly, but the private JSON reader
previously checked the path and later reopened it, without binding the read to
the exact previously inspected file. Stage373 uses a single open file descriptor,
checks normal-file type, bounds input to 4 KiB, verifies identity and size
before/after reading, detects symlinks and Windows reparse points, and rejects
non-finite JSON constants and duplicate keys. No raw MAME output is accepted.

The Stage371 owner-only preflight now must match **both** the known Stage369 ZIP
size (29,169,673 bytes) and the 19 synthetic checks it reported, in addition
to the already pinned archive digest and schema fields. UTC time must be a
valid ISO-8601 timestamp with explicit +00:00 or Z. These checks authenticate
neither the author of a JSON report nor the execution of MAME: they only
harden local classification and prevent accidental promotion.

The source tests are synthetic. Public GitHub Actions must never read the
private Stage369 capsule, actual Stage371 JSON, original dino ROM, INP or WLF.
Owner-held inputs and all derived reports remain in the private Google Drive
Project Evidence Archive with independent SHA-256 readback, rather than being
left only in ephemeral working directories.

Current runtime boundary:

1. Source-only and synthetic CI: eligible for public GitHub Actions.
2. Private Stage369 ZIP integrity and Stage371 preflight: **offline only**;
   a preflight grade is not a native MAME verification.
3. Real owner-controlled Windows MAME 0.106 `dino -verifyroms`: **not yet
   observed**; requires a genuinely isolated authorized Windows host.
4. Real `dino.inp` / `dino.wlf` replay and bounded trace: **not yet
   observed**; separate runtime and private evidence required.
5. Physical Nintendo Switch: **not yet observed**.

The earlier receipt tool keeps generating a local **self-report**, not a
cryptographic third-party attestation. Keep PR #139 Draft and do not merge to
main on the strength of this stage alone.

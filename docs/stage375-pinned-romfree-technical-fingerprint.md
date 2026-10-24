# Stage375 — immutable 12-component ROM-free MAME artifact pin

## Purpose

The Stage374 native-Windows probe verified the MAME 0.106 PE32/i386 executable
against an independent SHA-256 pin, but accepted the other technical artifact
members when their SHA-256 values merely agreed with the bundle's own
`SHA256SUMS.txt`. An attacker replacing a harmless technical file and rewriting
that self-contained manifest could therefore preserve the old `verify_bundle`
result.

Stage375 adds `verify_frozen_components` to the same Windows probe. It pins
the SHA-256 digests of **all 12 files**, including the manifest, pinned source,
driver XML, patches, executable, runtime status and source-pin. It rejects
extra or missing files, symbolic links, malformed expected digests, and member
changes even when the SHA256SUMS manifest is consistently rewritten.

Frozen reference:

- GitHub Actions technical build run: `39859311511`
- Technical artifact ID: `12461451785`
- Original outer ZIP SHA-256:
  `5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a`
- Size: 41,450,235 bytes
- Private backup on Drive:
  `1zd-A4B4-jMlug0oVRYmGa4k_yfFqL7T1`, under
  `07_Builds_and_Test_Artifacts`, not shared
- Windows ROM-free report from Stage374:
  `1yATW8FWP17sGpHApSXibgLzT_-ps7weP` under
  `03_Aggregate_Reports`, not shared

GitHub Actions already checks the public technical executable using
`verify_bundle` (8 internal hashes + source ID); Stage375 requires **both**
that check and the new frozen fingerprint (12 independent component hashes)
before running actual MAME CLI probes. The public synthetic tests now include
a rewritten self-consistent manifest that must nevertheless fail the frozen
fingerprint check.

The technical artifact in GitHub expires **2026-10-25**. The private Drive copy
is the durable reference; the GitHub workflow will need a compatible verified
source of this same ROM-free artifact after the source run expires. Do not
silently substitute an unpinned replacement or claim that the PR workflow is
permanently self-sufficient.

## Evidence boundaries

This checks provenance of a **ROM-free MAME technical artifact**, not the
owner-held original ROM, not replay of `dino.inp`, and not a Nintendo Switch
hardware run. It does not run the private Stage369 Windows capsule, and it does
not constitute a runtime attestation. A successful Stage375 technical test
cannot pass the Stage372/373 native-ROM evidence gate.

Private ROM, WLF/INP, source captures, extracted graphics and all game-derived
reports must remain on owner-only Google Drive according to the common Project
Evidence Archive standard, with fresh SHA-256 checks on upload/readback.
Keep PR #139 in Draft and `main` unchanged.

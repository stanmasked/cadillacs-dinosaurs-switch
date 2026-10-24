# Stage382 — historical MAME ROM-free CI artifact expiry guard

## Concrete issue

The Windows MAME 0.106 native ROM-free preflight used the fixed workflow
run ID `39859311511`. Its `historical-mame0106-runtime-rom-free`
artifact (ID `12461451785`) is scheduled to expire on
**2026-10-25 at 21:49:37 UTC**, and subsequent workflow runs would not
be able to download it. This artifact is **public technical tooling only**:
MAME executable, original upstream source, source patches, XML driver listing
and technical checksums. No original `dino` game ROM, `dino.inp`,
`dino.wlf`, gameplay captures, or derived original assets are included.

The existing owner-only Google Drive archive retains the exact 41,450,235
byte ROM-free technical ZIP, SHA-256:
`5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a`.
It is for durable owner-controlled recovery, **not** for public CI direct
download; no private Drive tokens or game bytes enter the workflow.

## Implemented

The source-only locator `tools/mame0106_romfree_artifact_locator.py`
queries GitHub's public repository artifact metadata through the read-only
`GITHUB_TOKEN` using bounded HTTPS requests. For each candidate, it
requires all of:

- Exact artifact name `historical-mame0106-runtime-rom-free`
- `expired=false` and an explicit future `expires_at` timestamp
- Exact ZIP byte size **41,450,235**
- GitHub's exact outer ZIP digest
  `sha256:5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a`
- A valid integer GitHub workflow-run ID, valid timestamps, not a future
  creation time; choose the newest otherwise-equivalent live artifact

The native Windows workflow first runs 14 synthetic-only selector regression
tests, selects the latest exact pinned build, downloads it using the returned
GitHub run ID, then still executes the previous independent native probe:
**8 public technical component pins, 12 complete frozen component pins,
real Windows `-help`, `-showconfig`, `-listxml`**, and the `dino`
driver listing. Selection is not permission to skip the post-download
checks.

No fallback to an unknown digest, unpinned ZIP, old cached binary,
user-controlled external URL or Google Drive is allowed. Missing/expired
matching artifacts are an explicit **CI failure**, not a silent pass.

## Renewal and remaining limitation

A legitimate source-only rerun was requested for the existing historical
`build-upstream-mame-0106` GitHub Actions job ID `120105587250`.
The fresh build must be allowed to finish and independently compared
against all frozen pins. If it reproduces the exact artifact digest, the
new artifact becomes eligible without hard-coding its run ID.

**This selector by itself does not create or permanently host a new
artifact.** Rebuilds are still required before every matching artifact
expires, or a separately audited durable technical distribution method is
required. Owner-only Drive retention remains the non-expiring backup, and
the private Windows MAME execution/INP playback gates remain separate.

The branch stays in Draft PR #139. Real
`MAME 0.106 -verifyroms dino`, original `dino.inp` playback, emulator
Switch gameplay, and physical Switch testing are **not** evidenced by
these ROM-free technical probes.

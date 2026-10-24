# Stage383 — freeze-preserving 90-day historical MAME 0.106 ROM-free renewal

## Context and source audit

On 2026-10-24 all five Stage382 GitHub Actions at `9f71c10b`
completed successfully. The previously pinned technical archive
`historical-mame0106-runtime-rom-free`, artifact ID `12461451785`,
was set to expire 2026-10-25 21:49:37 UTC.

Two successful upstream recompilations were investigated, *not assumed
reproducible*. All three outer ZIPs contain exactly 12 CRC-valid
public technical components. The 2026-10-24 compilations were different
from the 2026-10-22 frozen binary:

| Case | ZIP size | ZIP SHA-256 | Executable SHA-256 |
|---|---:|---|---|
| Frozen original | 41,450,235 | `5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a` | `a3b0526056c2ecd10415a5757f0085aa6977992feddbb232ca60c7c446f81d44` |
| Rebuild of original run | 41,450,398 | `9f6a1acec78c103013bbe516109b6636863703176d7ba5d0414e0097877e9bea` | `b62bb2a0ea0543b35a24029537fc5f3389f2d23b27fce075fbf4e7ba50575c3a` |
| New active PR rebuild | 41,450,399 | `f12ba8b5702c19b5b43a69379ba371f9bcb5f71fb67d9c128629e17f5b73dcd0` | `a0edfb699896fcab015fbbe090fbaa3816a7ea6874a15755746e26342f23dac3` |

The historical executable differs by 426 bytes in total size and
numerous internal bytes, not only timestamp bytes. The `-help` version
line and `dino-driver.xml` have the expected changing compiler date
(Oct 22 vs Oct 24, 2026), but that does **not** explain or authenticate
all EXE differences. Old/new technical patches, upstream source ZIP,
license, source pin, runtime status and `-showconfig` file checksums
match. Both rebuilt binaries are **rejected** by the frozen component
pins. There was no original ROM or input recording in any of these
public technical artifacts.

## Verified renewal, without recompilation

A first attempted workflow run `40070334557` was refused. It used
`actions/download-artifact@v4` with the old *run ID and artifact
name*; GitHub picked a newer artifact from an attempt with the same
name, proving this selection was ambiguous. The mandatory 8-pin
validator caught the incorrect executable and failed closed. No
unverified package was published.

The corrected
`.github/workflows/mame0106-romfree-golden-renewal.yml` instead
downloads the **exact original artifact ID `12461451785`** through
the GitHub artifact API. It verifies the complete original outer
ZIP SHA-256 **before extraction**, independently audits the 12
immutable internal SHA-256 values and 8 source/technical manifest
values, and republishes only those exact public technical files with
90-day GitHub Actions retention. No historical game data or MAME game
execution occurs during renewal.

The successful renewal is [GitHub Actions run #40070433630](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/40070433630).
The new 90-day artifact has:

- Artifact ID: `12551316232`
- Name: `historical-mame0106-runtime-rom-free`
- ZIP size: **41,450,235 bytes**
- Outer ZIP SHA-256:
  `c9296bcc2608dae2ab82494ea89ad6a5f3850a3e145fce620272b798858bb53a`
- GitHub expiration: **2027-01-22 06:29:55 UTC**
- 12/12 internal files: **byte-identical** to frozen original
- ZIP CRC: pass
- Private game data used: **none**

The differing outer ZIP SHA is a transport-format difference; it
does **not** imply changed internal technical contents. It was
independently verified from a fresh download using an exact
per-member SHA-256 comparison.

## Long-term storage

Both historical artifacts and their technical source provenance are
recoverable from owner-only Google Drive. The new exact renewed ZIP is
stored as
`Stage383_Golden_ROMfree_MAME0106_12ExactComponents_90day_Run40070433630.zip`
in `07_Builds_and_Test_Artifacts`, file ID
`1vvoacxrN0HOvvsU9iUaCQZTnvo1KtoXE`.
Its **Google Drive readback** verified the complete outer SHA,
41,450,235 byte size, CRC, inventory and all 12 immutable component
hashes; file permission is **owner-only**, `shared=false`.

The public locator `tools/mame0106_romfree_artifact_locator.py`
now contains a **fixed two-element allowlist** of independently
audited outer ZIP digests: original and renewed. It refuses the two
non-reproducible rebuilt binary digests and every unknown ZIP. The
native Windows ROM-free preflight continues to inspect every frozen
internal component before running MAME technical commands.

The 90-day artifact still eventually expires; this release does not
automatically guarantee future renewal. New renewal must not read
game ROMs or use mutable unpinned sources, and must not silently
extend trust to compiled files with different checksums.

None of these ROM-free checks proves owner-private original
`-verifyroms dino`, WolfMAME 0.106 original `dino.inp` playback,
real arcade graphics capture or physical Nintendo Switch hardware
performance. Draft PR #139 remains open, `main` unchanged.

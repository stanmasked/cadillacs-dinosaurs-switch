# Stage374 — preserve ROM-free MAME technical artifact and recheck on native Windows

## Permanent technical archive (owner-only Google Drive)

The source-built, **ROM-free** MAME 0.106 artifact from GitHub Actions
run `39859311511`, artifact ID `12461451785`, expires on
**2026-10-25** in GitHub. Its separately saved Google Drive copy
`mame0106-romfree-technical-bundle-run39859311511-20261024.zip`
was downloaded and independently compared byte-for-byte by SHA-256:

- Size: **41,450,235 bytes**
- ZIP SHA-256: `5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a`
- ZIP CRC roundtrip: all **12 entries**, no errors
- Google Drive ID: `1zd-A4B4-jMlug0oVRYmGa4k_yfFqL7T1`
- Owner-only: Google metadata reports **not shared**, one owner permission
- Folder: `07_Builds_and_Test_Artifacts` in the Cadillacs and Dinosaurs Remake
  evidence archive, not the public repository

This is a technical, source-built MAME bundle. It is not the original game ROM,
the `dino.inp` recording, `dino.wlf`, graphics, or a game-derived capture.
Its archived copy remains available after the short-lived GitHub artifact expires.
Avoid duplicate uploads or overwriting original evidence.

## Independent Windows gate

The workflow `.github/workflows/mame0106-windows-romfree-preflight.yml`
now runs also on PR changes to the native probe, its synthetic tests or the
workflow itself. On `windows-2022` it:

1. Runs the ROM-free synthetic technical bundle regression suite.
2. Refuses presence of original game files in public source checkout.
3. Downloads only pinned source-built ROM-free MAME technical artifact.
4. Validates expected technical ZIP contents via per-file SHA-256, pinned
   upstream source ID, PE32-i386 executable hash.
5. Starts the genuine technical MAME executable under native Windows for
   `-help`, `-showconfig`, `-listxml` (bounded execution, no ROM input).
6. Checks options needed for bounded capture and historical `dino` driver.
7. Publishes at most a small ROM-free technical summary, retention 3 days.

The Windows test is **real MAME binary command-line execution** but is not
real game execution. It cannot substitute for a private Windows host with the
owner-only Stage369 capsule and full `dino -verifyroms` result, and never
claims playback of the original input recording.

The original gameplay assets, all future `-verifyroms` receipts, INP replay,
raw captures and SHA-256 manifest should remain in owner-only Google Drive
with independent download/readback checks. PR #139 stays Draft and `main`
must not be merged until the real evidence gates are satisfied.

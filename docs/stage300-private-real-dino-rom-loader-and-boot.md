# Stage300 — genuine original dino ROM loader and bounded boot gate (private only)

Stage299 privately recovered the original user's `Cadillac Dinosaur.zip`
from their connected Google Drive and matched **all sixteen** ROM
contents by both CRC32 and SHA-1 against historical MAME 0.106
`src/drivers/cps1.c:ROM_START(dino)`. It then prepared
a clean **private** `dino.zip` under canonical MAME
filenames. The original game ROM and derived file are not public and
must never be committed, attached to a PR, posted in CI or published
in a release.

Previously validated historical MAME 0.106 **really executed a synthetic
Minivader test** and captured identical changing frames across two
replays. That is **not** evidence that the original dino ROM loaded.

## Goal of Stage300

Add a real, local-only **original dino ROM acceptance gate** separate
from historical WolfMAME INP playback. The stage requires neither
`dino.inp` nor `dino.wlf`,
which are currently unavailable in the active execution container.

New tool: `tools/mame0106_private_dino_boot_probe_300.py`.

Before launching a private MAME process, the tool enforces:

1. A private folder containing **`dino.zip`** outside the public
   repository, with no symlinked parent directory.
2. The **same complete 16-member content verification** that passed
   Stage299: size, CRC32 and full SHA-1 against the upstream
   historical MAME 0.106 dino manifest.
3. A private, regular executable; optionally a Stage294 **candidate
   unsigned artifact bundle** integrity check. Bundle consistency
   alone is not cryptographic provenance attestation.
4. Actual MAME process must return a recognizable **M.A.M.E. v0.106**
   or **MAME 0.106** version banner, with exactly bounded subprocess
   output and a timeout. Stage300 fixes an older regex that incorrectly
   rejected the historical dotted `M.A.M.E.` banner.
5. A successful actual **`-verifyroms dino`** subprocess
   with exit code zero and the expected dino ROM-set confirmation.

## Option A — source ROM verification + *real MAME ROM loader*

Run on a private Windows machine with the historical instrumented
MAME 0.106 executable from Stage290 (not a current MAME build):

~~~bat
python tools\mame0106_private_dino_boot_probe_300.py ^
  --emulator C:\private\mame290-bundle\mame0106.exe ^
  --runtime-bundle C:\private\mame290-bundle ^
  --rom-dir C:\private\roms ^
  --out C:\private\audits\stage300-loader.json
~~~

On success, the exact status is:

`REAL_MAME_DINO_ROM_LOADER_ACCEPTED_GAMEPLAY_NOT_VERIFIED`.

It means the original dino ROM bytes matched the public reference
**and** a **real MAME process** confirmed the dino ROM set. It does
not mean any graphical frame was played.

## Option B — bounded real game boot with MNG

After Option A is successful, request a short local-only boot video:

~~~bat
python tools\mame0106_private_dino_boot_probe_300.py ^
  --emulator C:\private\mame290-bundle\mame0106.exe ^
  --runtime-bundle C:\private\mame290-bundle ^
  --rom-dir C:\private\roms ^
  --boot-frames 240 --seconds 300 ^
  --capture-out C:\private\audits\stage300-boot.mng ^
  --out C:\private\audits\stage300-boot.json
~~~

The tool creates an isolated temporary workspace and requests exactly
240 video callbacks from the original dino driver. Its MAME process
never supplies any user INP or WLF, and uses no fake controller input.

The run must exit with code zero and create a genuine **MAME MNG movie**.
The PNG/MNG integrity parser separately validates chunk CRCs, decoded
scanlines, dimensions, and **exactly 240 frames**. Nonzero exit,
timeout, missing MNG, malformed PNG and frame count mismatch have
distinct failure statuses.

The optional private movie is retained **exclusively** to a fresh path
with restrictive permissions. No user paths, private file hashes,
ROM bytes, original game frames or diagnostic subprocess output are
printed or copied into the JSON receipt. All attempts to place those
outputs inside the repo are rejected.

Exact success status:

`CANDIDATE_REAL_DINO_MNG_BOOT_VALID_UNAUTHENTICATED`.

This is evidence of a valid boot-video **candidate** but not proof
that the user-provided INP replayed, WolfMAME provenance, exact
video/input correspondence, or parity with the planned Switch remake.

## Distinct failure statuses

- `BLOCKED_DINO_ROM_CONTENT_NOT_CONFIRMED` — local archive
  did not pass Stage299's source-grounded hash audit.
- `BLOCKED_MAME_RUNTIME_BUNDLE_INCONSISTENT` — selected
  executable disagreed with the supplied private candidate build bundle.
- `BLOCKED_MAME_0106_HELP` — unrecognized emulator version.
- `BLOCKED_REAL_MAME_DINO_ROM_LOADER` — real process did
  not accept the original dino ROM.
- `BLOCKED_DINO_BOOT_PROCESS` / `BLOCKED_DINO_BOOT_NONZERO_EXIT` —
  boot failed or timed out.
- `BLOCKED_DINO_BOOT_MNG_MISSING` /
  `BLOCKED_DINO_BOOT_MNG_INVALID` /
  `BLOCKED_DINO_BOOT_FRAME_COUNT_OR_AUDIT` —
  missing/corrupt/incomplete movie.
- `BLOCKED_PRIVATE_DINO_BOOT_SETUP` — a private
  path, argument, file or preflight guard was invalid.

Every receipt explicitly keeps the original INP replay,
WolfMAME provenance, input-to-video mapping, gameplay parity,
and physical Nintendo Switch flags **false**.

## Public regression suite

~~~sh
python -m unittest discover -s tests -p 'test_mame0106_private_dino_boot_probe_300.py' -v
~~~

These test only tiny invented fake archives and fake process results.
Public CI **cannot** execute the original dino game because the
original ROM remains private, nor is the historical Windows MAME
rebuilt in Stage300 because its C code is unchanged.

## Outstanding real test

The private original `dino.zip` is available locally in the
session, but there is **no installed historical MAME executable** in
the available runtime (nor Windows Wine), and original `dino.inp`
and `dino.wlf` still are not mounted.

Therefore this new gate's public CI result is **synthetic validation
of the code**. The original dino loader and actual boot are
**not verified until the private Windows run above is executed**.

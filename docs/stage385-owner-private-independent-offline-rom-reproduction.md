# Stage385 — independent owner-private recheck of Stage384 original ROM content

## Baseline (Stage384 and Stage383)

Stage384 recorded an owner-private, genuine **offline content audit** of the
original `dino` ROM payloads: all 16 expected files matched the pinned
MAME 0.106 historical `-listxml` driver by filename, size, CRC32 and SHA-1
(7,995,392 uncompressed bytes). Its owner-only report's SHA-256 is
`8aa4b3e71bdb70150abf9a8ed38287fe4c7471ba994324cf953cbdfbcb5fe47f`.

Stage383 retained the original ROM-free technical MAME executable and XML
driver without recompiling or replacing either. The archived owner-only
Stage369 capsule remains untouched and has outer SHA-256
`fa6ff589b109db70c8231bf7713ec50cf5b9a15b58e43bb3b6705bc25e4bd19d`.

The previous Stage384 revision `b91ec377` passed native Windows ROM-free
preflight, Windows PowerShell synthetic tests and the privacy gate. The
Python CI and Switch bootstrap were still running when Stage385 began.
Those results are technical/synthetic evidence, not original ROM execution.

## Reproduction implemented

Added `tools/mame0106_private_stage385_reproduce.py`. This is a
**private-host-only offline** verification command, which:

1. Rejects GitHub Actions and new output paths inside the public repo,
   symlinked output parents and existing report files.
2. Verifies the exact private Stage384 JSON report SHA-256, schema,
   evidence grade, input hashes, 16-member result and all explicit
   `native_mame_process_executed=false`, `inp_playback_executed=false`,
   `physical_nintendo_switch_executed=false` claims.
3. Verifies the entire exact golden ROM-free Stage383 ZIP outer SHA-256
   `c9296bcc2608dae2ab82494ea89ad6a5f3850a3e145fce620272b798858bb53a`,
   all **12 immutable internal file hashes**, CRCs and inventory.
4. Uses the existing Stage369 capsule validator to check the outer
   Stage369 SHA-256, exact 4-part inventory and fixed SHA-256 of the
   historical MAME EXE, original ROM and PowerShell validator.
5. In a temporary, private, cleaned directory, stages only the ROM ZIP
   and historical XML; reruns the existing production offline ROM auditor
   against the source-pinned driver, checking **all 16 source file CRC32,
   SHA-1, exact uncompressed lengths and expected filenames**.
6. Refuses any result other than `16/16` and `7,995,392` bytes, and
   writes an exclusive, small, owner-private Stage385 JSON receipt with
   only input digests, counters and explicit non-execution flags.
7. Never executes MAME, processes original INP/WLF, publishes a ROM,
   or claims native Windows attestation.

Use only on an owner-private host; replace paths with actual local private
locations (never place them in public GitHub):

```bash
python -m tools.mame0106_private_stage385_reproduce \
  --capsule "/private/Stage369_MAME0106_Private_Windows_Verify_Capsule.zip" \
  --golden-zip "/private/Stage383_Golden_ROMfree_MAME0106_12ExactComponents_90day.zip" \
  --stage384-report "/private/Stage384_Private_Dino_ROM_Offline_CRC_SHA1_Audit.json" \
  --output "/private/Stage385_Private_Offline_ROM_Reproduction_Receipt.json"
```

## Confirmed genuine private read and results

On 2026-10-24, the published Stage385 code was independently extracted from
the GitHub Windows synthetic CI **source-only** artifact and run against the
real owner-private Stage369 capsule, original Stage383 golden archive and
unchanged owner-private Stage384 report. It returned:

```text
status=verified_offline_only
rom_members_verified_crc32_sha1=16
native_mame_process_executed=False
original_inp_playback_executed=False
```

The resulting 1,059-byte Stage385 owner-private receipt has SHA-256
`1aec9e864511bff53319be27213a3dccc327ba46391cfdf5bd4b1b9b52815d7b`.
The 3,716-byte source-only CI ZIP has SHA-256
`f742fc5bd62f27abda66659eb662f5fc11b888648bd5a33f90848212c5620489`.
The private evidence manifest is 1,140 bytes, SHA-256
`86248d58c3472a3b229682697b658c9052891f59211a0865b86407c929503a82`.

Their owner-only Google Drive locations:

- `03_Aggregate_Reports/Stage385_Private_Offline_ROM_Reproduction_Receipt.json`,
  file ID `14EsUeYPT6ZxuWZrtgrj1hzAJaOZEXR0J`
- `07_Builds_and_Test_Artifacts/Stage385_Private_Offline_Auditor_Source_Only.zip`,
  file ID `16eEmigDlQ9y3z691z6UtY2kUoNPFnoRv`
- `00_Manifest_and_SHA256/Stage385_Private_Evidence_Manifest.json`,
  file ID `1iHQIzn2jup0gx3tEUh-RhBpz51kOcMA1`

All three were verified by downloading back from Google Drive and comparing
exact SHA-256 and length. All three are owner-only, `shared=false`.
No original ROM, extracted resources or raw captures were sent to GitHub.

## Synthetic Windows regression

`tests/test_mame0106_private_stage385_reproduce.py` exercises an actual
CRC/SHA-1 recheck of **16 synthetic** payloads with historical parser
requirements, plus wrong archive hash, changed component inventory, changed
or duplicate-key Stage384 report, NaN, output overwrite and parent symlink
refusal, and GitHub Actions privacy refusal. The public CI uses only
synthesized data and uploads only the public-source-only module.

## Remaining blocked gate

This is **independent offline validation**, not evidence of executing the
original game inside MAME. The available Linux container's Wine32/QEMU
cannot launch the Windows i386 MAME executable. The authentic native
`MAME 0.106 -verifyroms dino` step, `dino.inp` playback and
Switch emulator/hardware testing remain **not executed**.

Do not promote the Stage385 JSON into native success. Reuse the owner-only
Stage369 original and Stage381 trusted private-Windows helper on a
compatible owner-controlled Windows host when available. PR #139 remains
Draft; no merge to `main`.

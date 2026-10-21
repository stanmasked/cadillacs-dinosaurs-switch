# Stage301 — genuine historical Windows artifact manifested checksums

## Actual private inputs available

The original game ROM was previously retrieved from the user's connected
Google Drive and locally normalized into a private, canonical `dino.zip`
outside GitHub. Stage299 verified all sixteen expected ROM file CRC32
and SHA-1 checksums against public source-pinned MAME 0.106.

In Stage301, the **actual code-only historical Windows MAME 0.106
GitHub Actions artifact** from the successful Stage297 run
was retrieved privately:

https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39672614529

Artifact name: `historical-mame0106-runtime-rom-free`.

No ROM or original gameplay files are included in that downloadable
artifact. Its Windows MAME executable is a 32-bit PE32 x86 binary,
with the in-process MNG input-count instrumentation.

## Actual bundle audit and bug fixed

Before this stage, the Stage294 validator understood only this
single form of a GNU `sha256sum` record:

    <64-lowercase-hex-digits><space><space>filename

But the real historical MAME artifact's `SHA256SUMS.txt`
contains the equally standard **binary mode** form:

    <64-lowercase-hex-digits><space>*filename

The actual bundle contained exactly eight expected manifest records.
An independent private check read every actual payload and confirmed
**8/8 SHA-256 matches**. The original MAME source archive within the
artifact was also inspected; the `ROM_START(dino)`
declarations require exactly sixteen files. Every one of the sixteen
private canonical `dino.zip` members matched both
the original source CRC32 and full SHA-1 values.

However, the prior Stage294 manifest regex rejected the valid binary
`*` marker. This is a **real artifact integration bug**, not
a synthetic test artifact discrepancy.

Stage301 fixes the narrow issue in
`tools/wolfmame0106_private_runtime_bundle_gate.py` by accepting
**either** GNU `sha256sum` text or binary record forms, while
still rejecting noncanonical names, duplicate entries, unexpected
members, path traversal, malformed markers, mutated checksums and
missing original patch/driver/version evidence.

Four new regression tests use **invented, synthetic executable and
file bytes**, including an exact reproduction of the actual GNU
binary-mode SHA256SUMS format. These are ordinary ROM-free tests.

## Local-only procedure

Extract the historical ROM-free GitHub Actions artifact to a
**private, fresh external folder**. The actual original ROM must live
separately in a private directory outside the project tree.

Inspect bundle consistency:

~~~bat
python tools\wolfmame0106_private_runtime_bundle_gate.py ^
  --runtime-bundle C:\private\mame290-bundle ^
  --emulator C:\private\mame290-bundle\mame0106.exe ^
  --out C:\private\audits\stage301-bundle.json
~~~

The exact successful label is:

`CANDIDATE_RUNTIME_BUNDLE_CONTENT_CONSISTENT_UNAUTHENTICATED`.

This asserts candidate **internal consistency**, not independent
cryptographic attestation of the artifact's GitHub origin or
WolfMAME provenance. Its SHA-256 manifest and source pin are unsigned.

Then, on a **compatible private Windows host**, use the Stage300
private original-game loader command:

~~~bat
python tools\mame0106_private_dino_boot_probe_300.py ^
  --emulator C:\private\mame290-bundle\mame0106.exe ^
  --runtime-bundle C:\private\mame290-bundle ^
  --rom-dir C:\private\roms ^
  --out C:\private\audits\stage301-real-dino-verifyroms.json
~~~

This last command is not yet executed in the current runtime.
Only a **real MAME subprocess**, not static artifact or ROM checksum
matching, can establish that the original game passed
`-verifyroms dino`.

## Strict evidence boundary

The current environment provides the complete Windows PE32 binary
and the full private original ROM but **not an available Windows PE
runtime**. No Windows MAME process was executed here.

Thus Stage301 has verified:

- all eight runtime-bundle file SHA-256 checksums;
- executable PE32 architecture and source-pinned patch metadata;
- exactly sixteen dino game ROMs with CRC32 and SHA-1 matching the
  actual MAME 0.106 source tree's `ROM_START(dino)`.

Stage301 **does not yet verify** original `dino` ROM-loader
acceptance by a running MAME, real game boot/captured pixels,
original user INP/WLF playback, WolfMAME-specific binary provenance,
input-video causality or a physical Nintendo Switch.

Never upload original game ROM, INP/WLF, game images, MNG or private
input/output receipt data to public GitHub or its CI artifacts.

# Stage294 — private Windows MAME 0.106 bundle consistency gate

The main remaining limitation is that the original user-provided dino ROM,
INP and WLF are not accessible in the current execution environment.
Public GitHub Actions can build and test **instrumented historical MAME**,
but it cannot claim original-game playback. Stage294 closes a separate,
testable risk: accidentally using an arbitrary, outdated or differently
compiled MAME executable for a private Stage292 experiment.

## Reference candidate bundle

Stage290 GitHub Actions successfully built ROM-free Windows MAME 0.106.
The workflow artifact is named `historical-mame0106-runtime-rom-free` in:

https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39654679931

GitHub Actions artifacts have limited retention. If the artifact has
expired, its build workflow must be reproduced using the pinned upstream
source and checked-in instrumenting patch. The archive is public and
**must contain no original game data**.

The extracted candidate bundle contains:

- `mame0106.exe` — 32-bit historical MAME Windows executable,
  instrumented to log MNG callback and successful INP-port read counters;
- `SHA256SUMS.txt` — SHA-256 manifest for eight code-only artifacts;
- `source-pin.txt` — pinned tag/commit and build/test metadata;
- `mame0106-source.zip` — public historical MAME source archive;
- three code-only compatibility/window/trace reproduction patches;
- `dino-driver.xml`, `mame0106-help.txt` and
  `mame0106-showconfig.txt` — outputs of ROM-free smoke checks.

## Audit local extracted bundle without running gameplay

Extract the exact archive to a new private directory outside GitHub,
for example `C:\private\mame290-bundle`. Its members and
parent directories must be regular and free of symlinks. Then execute:

~~~bat
python tools\wolfmame0106_private_runtime_bundle_gate.py ^
  --runtime-bundle C:\private\mame290-bundle ^
  --emulator C:\private\mame290-bundle\mame0106.exe ^
  --out C:\private\audits\mame294-gate.json
~~~

This **read-only** audit checks each of the eight files against the
bundled SHA-256 manifest, compares the selected executable against the
manifested executable digest, checks for Windows PE32 x86 format, and
requires the source-pin to name the precise pinned historical MAME tag
and revision:

`mamedev/historic-mame / mame0106 / 0a83d596c83b4d1a72cb3a7b1d2835b809206f2f`

It also verifies that the combined trace source patch contains
in-process input-read and video-callback instrumentation, and that the
stored CLI help, configuration and driver XML contain expected features.
Original Windows help/config/XML may use CRLF line endings.

The result is written **exclusively** to a new private JSON file. It
contains only bounded boolean verification outcomes and the label
`CANDIDATE_RUNTIME_BUNDLE_CONTENT_CONSISTENT_UNAUTHENTICATED`.

**Important:** the manifest and source metadata are unsigned and can be
edited together with the files. These checks verify that the *supplied*
files are internally consistent with the expected Stage290 layout.
They do **not** cryptographically attest that GitHub built the files,
independently authenticate binary provenance, confirm WolfMAME
anti-cheat code, demonstrate real dino replay, or prove that the
input and video frame counters correspond causally.

## Optional preflight during Stage292

The existing one-command Stage292 private runner now supports an optional
bundle check **before starting any game process**:

~~~bat
python tools\wolfmame0106_private_two_window_experiment.py ^
  --runtime-bundle C:\private\mame290-bundle ^
  --emulator C:\private\mame290-bundle\mame0106.exe ^
  --rom-dir C:\private\roms ^
  --inp C:\private\recordings\dino.inp ^
  --wlf C:\private\recordings\dino.wlf ^
  --out-dir C:\private\audits\experiment-002 ^
  --first-start 36000 --frames 1200 --shift 600 --seconds 1800
~~~

If a bundle is supplied but fails validation, Stage292 exits before
spawning a child process or creating the experiment output folder.
The option is additive for compatibility with previous local use;
for any real original-game experiment, using the bundle check is
strongly recommended.

Never include actual ROMs, INP/WLF recordings, MNG captures, game
images or private receipts in public GitHub releases, issues, CI
artifacts or source commits.

## CI

~~~sh
python -m unittest discover -s tests -p 'test_wolfmame0106_private_runtime_bundle_gate.py' -v
~~~

The tests use synthetic Windows PE headers, synthetic source metadata,
and fake SHA-256 manifests. Tests explicitly verify that passing the
consistency gate leaves all real-playback and provenance flags **false**.
This is not a claim that a synthetic fake file is an executable MAME.

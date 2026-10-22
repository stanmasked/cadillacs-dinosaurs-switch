# Stage310 — prepare an entirely ROM-free diagnostic SD folder

Stage309 established complete host-native C/Python parity for all fourteen
*invented* CPS-1 scenes. Stage310 creates a ready-to-copy **two-file SD
folder** containing only the Stage308 artificial graphics and the Stage307
synthetic scene sequence. It does not use or read an original game archive.

## Generate a new private folder

Choose a **new**, nonexistent folder under an existing external private
directory. Do not point this at your live SD card, the repository, or a
location containing any original `gfx.bin`.

~~~sh
python tools/cps1_rom_free_sd_bundle_310.py \
  --out-dir /private/dino-rom-free-new-310
~~~

The command writes this structure only on success:

~~~text
dino-rom-free-new-310/
  rom-free-install-ready.json
  switch/
    cadillacs-dinosaurs-switch/
      gfx.bin
      sequence.bin
~~~

- `gfx.bin`: **4,194,304 bytes** of deliberately artificial planar CPS-1
  data, generated from a public fixed textual seed.
- `sequence.bin`: **875,160 bytes**, fourteen invented CPS-1 frame states
  at 2 FPS; these frames are **not** gameplay.
- `rom-free-install-ready.json`: local-only manifest with byte counts,
  SHA-256 fingerprints of these **invented files only**, verified readback,
  synthetic provenance flags, and explicit non-verification flags for real
  game playback, original ROM and physical Switch/emulator display.

The two binaries total **5,069,464 bytes**, excluding the JSON manifest.

To try the existing NRO in a Nintendo Switch or compatible emulator,
copy the contents of the generated `switch/` directory to the root of a
**separate diagnostic SD environment**. Never overwrite the user's
original graphics or saved data. Keep the manifest on the host; it is
only a private provenance record and is not required by the NRO.

The viewer supports pause, step and speed controls for the fourteen
scenes (Stage307). Its rendering will show intentionally fabricated
pixels, **not original Cadillacs and Dinosaurs artwork or gameplay**.

## Failure rules

The staging root must not exist and must be outside the GitHub checkout.
A symlinked root or parent is refused. All folders are private (0700);
both data files and the final receipt are created exclusively (0600).
Before writing anything, **both files must match the byte-exact outputs of
the canonical ROM-free generators**. A matching size, marker, repeated
graphics block, syntactically valid CPS1SCN1 frames, or recalculated CRCs
are explicitly insufficient to claim synthetic provenance. Both staged
files are then checked for exact length and SHA-256 readback before the
manifest is written. The generator refuses overwrite or unrelated
data and never changes GitHub source files or `main`.

A crash/write failure may leave a **partial external staging directory**
without a final manifest. Such a directory is **not ready**. Discard it
manually without copying it to a Switch; do not retry onto the existing
directory. No automatic cleanup removes another process's files.

## Reproduce CI

~~~sh
python -m unittest discover -s tests \
  -p 'test_cps1_rom_free_sd_bundle_310.py' -v
~~~

The test suite is ROM-free and verifies staging structure, size,
permissions, readback, manifest truthfulness, repeat staging refusal,
symlink protections, wrong artificial graphics, corrupt scene sequence,
partial-write fail-closed behavior and redaction of external paths.

**Evidence boundary:** A successful local SD staging command proves only
the structure and integrity of *synthetic files*. It does not establish
that a Nintendo Switch or emulator loaded them, nor does it verify
original MAME 0.106 ROM execution or historical INP/WLF replay. Stage310
remains Draft, stacked on Stage309; the public ROM-free privacy gate is
unchanged.

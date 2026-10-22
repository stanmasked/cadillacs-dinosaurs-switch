# Stage315 — private original CPS-1 graphics with synthetic scenes on Switch SD

Stage314 confirmed 14/14 **artificial** scene frames visible in the
NeXium window across two independent clean boots. The remaining
question is whether the existing Switch NRO can consume authentic,
source-verified original CPS-1 *graphics* while preserving the same
independent, deliberately artificial scroll/OBJ/palette/priority states.

**This document does not claim original gameplay.** Stage315's public CI
cannot read, recreate, or publish the user's original ROM. Authentic
input processing requires a **private local** 16-member canonical
historical MAME 0.106 `dino.zip` outside the public source tree.

## Privately stage input, without publishing any asset

On the computer where the already-authorized canonical private ROM exists:

```sh
python3 tools/cps1_private_original_gfx_synthetic_sd_315.py \
  --rom /private/roms/dino.zip \
  --out-dir /private/staging/dino-stage315-new-sd
```

The destination **must not exist**, must be outside the repo, and must
have no symlinked parent. The source must be a regular private
`dino.zip` file, with no symlinked parents or public repository path.
If the private archive is still under the historical alternative source
names, first normalize it *privately* with the existing
`tools/mame0106_private_dino_rom_canonicalize_299.py`; never publish
the resulting ZIP.

Before creating any output, the tool verifies all sixteen original
MAME 0.106 ROM payloads by source CRC32 and full SHA-1, then reconstructs
the **exact** 4,194,304-byte CPS-1 graphics region. Existing Stage304
lane-order reconstruction is reused (not reinvented). The other ROM
payloads, including CPU and QSound, are verified but **not** exported
to SD. No executable original game program is included.

Separately, it generates the byte-exact Stage307 14-frame artificial
CPS1SEQ1 file at 2 FPS. It revalidates artificial scene provenance.
The output is created with restrictive permissions and exact private
readback before a success receipt is emitted:

```
new-sd/
  switch/
    cadillacs-dinosaurs-switch/
      gfx.bin             # authentic derived private graphics: DO NOT UPLOAD
      sequence.bin        # invented scene RAM/palette/objects: 14 frames
  private-original-graphics-synthetic-scenes-ready.json
```

Copy **only into your own private local SD** when running the normal
viewer NRO. No need to modify the public NRO or its ROM-free training
room. The Stage313/314 special synthetic optical proof does **not**
activate on genuine graphics, by design; a completed private SD staging
receipt does **not** count as NeXium execution or display verification.

## Safe evidence contract

A successful local receipt records only:

- Sixteen source-hash-verified original ROM members, number of graphics
  bytes privately staged, fourteen artificial scene frames and 2 FPS.
- Byte-exact readback for graphics and sequence, with no file hashes,
  original ROM bytes, sample pixels, private paths or original filename
  lists beyond public diagnostic constants.
- Explicitly FALSE fields for original MAME gameplay, original VRAM or
  palettes, movie/INP/WLF replay, original-graphics NeXium display, and
  physical Nintendo Switch display.

Staging is **not gameplay**, authentic MAME movie playback, original
VRAM/palette recovery, or permission to redistribute game content. The
files `gfx.bin`, private `dino.zip`, original screenshots, MNG/INP/WLF
and any derivative graphics must stay out of public branches, GitHub
CI logs, actions artifacts, PRs and releases.

## Public regression tests

```sh
python3 -m unittest discover -s tests \
  -p 'test_cps1_private_original_gfx_synthetic_sd_315.py' -v
```

These tests use intentionally invented byte patterns, mock verification
objects and a dummy file called `dino.zip` that is **not a real ROM**.
They verify preflight-before-write, complete evidence refusal, safe
paths/modes, exclusive output, exact readback, fake Stage308 marker
rejection, and CLI data-leak safety. They do **not** demonstrate a true
historical ROM or Nintendo Switch guest execution.

After a private staging pass, the next genuine milestone is a
**private opt-in original-graphics host/guest pixel test** comparing the
genuine original graphics region combined with the *known synthetic
scene state*, and later a separate, genuine historical MAME frame
capture for original VRAM/palette/input state. Neither follows from
Stage314's two ROM-free emulator boots.

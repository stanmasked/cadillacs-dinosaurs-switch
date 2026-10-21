# Stage309 — native C sequence acceptance and full synthetic frame parity

Stages 307–308 create a private, entirely artificial pair of files for the
existing Nintendo Switch NRO: a fourteen-scene `sequence.bin` and a four-MiB
synthetic planar `gfx.bin`. Stage309 checks both as a coherent input to the
**actual portable C source** compiled in the Switch build.

This is an in-memory **host diagnostic**; it is not a Nintendo Switch hardware
test, original MAME gameplay recording or the reproduction of the arcade ROM.

## Run ROM-free acceptance

~~~sh
python tools/cps1_rom_free_native_sequence_acceptance_309.py
python -m unittest discover -s tests \
  -p 'test_cps1_rom_free_native_sequence_acceptance_309.py' -v
~~~

The acceptance script generates known synthetic fixtures in memory, compiles
`cps1_tile.c`, `cps1_scene.c`, and `cps1_sequence.c` using GCC, lets the
C sequence decoder parse all fourteen genuine `CPS1SCN1` frames inside
`CPS1SEQ1`, renders them using the artificial graphics, then compares every
opaque RGBA pixel with a separately implemented Python compositor.

Coverage gates:

- Exactly **14** C-accepted frames, at 384 × 224 pixels each
  (**1,204,224** RGBA pixels compared).
- Exactly **zero** C/Python differing RGBA pixels.
- All **10** controlled priority/palette comparisons preserve their
  intended single-factor input changes and expected effects, including the
  pen-15 transparency invariants.
- C frame decoder rejects out-of-range access.
- Native sequence parser refuses damaged headers, inner CRC tampering even
  when outer CRC is repaired, and invalid layer-enable/reserved bytes even
  with *both* CRC values repaired.
- Native 60-Hz step/pause/speed controls match known frame wrap timing.
- Report explicitly denies original-ROM, original gameplay, private assets,
  source input replay, or physical-device verification.

The script writes **no graphics, frames, image hashes, ROM files or original
captures to disk or public CI artifacts**. Only a bounded aggregate JSON
status is printed. The temporary host C binary contains only public portable
source code and is discarded automatically.

## Evidence boundary

Successful Stage309 CI confirms the portable native C code can decode the
synthetic sequence and render all fourteen frames in host tests. It does
**not** establish that a Switch, Switch emulator, arcade ROM or historical
MAME was executed; no claim of actual console frame parity is made.

Keep PR Draft, stacked on Stage308. Never merge solely based on ROM-free CI.

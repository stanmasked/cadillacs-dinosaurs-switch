# Stage279 — private WolfMAME 0.106 binary/ROM readiness gate

Stage278's native input checkpoints are **not** original gameplay frames.
Before using any captured images as a CPS-1 reference, we need a real
WolfMAME 0.106-family executable, a locally held compatible ROM set, and
an authenticated replay of the actual INP. This stage closes only the
**first two environmental checks**, and cannot manufacture playback evidence.

## Run on the private workstation

Supply the user's own `dino.inp` and `dino.wlf`, a local executable
WolfMAME 0.106 command-line binary and a private ROM directory. Keep these
outside the public repository:

```sh
python3 tools/wolfmame0106_private_binary_gate.py \
  --emulator /private/wolfmame/mamep106 \
  --rom-dir /private/roms \
  --inp /private/dino.inp \
  --wlf /private/dino.wlf \
  --out /private/audits/stage279-wolfmame-readiness.json
```

For historical binaries, the `-help` banner may say either `MAME 0.106` or `WolfMAME 0.106`: the gate checks only the announced engine version, never treats that banner as proof that a WolfMAME build was used. Exact binary identity must be checked independently.

The sample paths are **placeholders** and the script will not create them.
No copyrighted files are fetched or staged in GitHub. A missing executable
or ROM directory gets an explicit blocked status. `-help` must visibly
advertise WolfMAME 0.106; then `-verifyroms dino -rompath DIR` must exit
successfully and report a good/best-available `dino` set. The `dino.inp`
and `dino.wlf` pair is checked against the pre-existing Stage270
structure reader. Failure of one gate cannot produce readiness.

The tool never runs `-playback` or a game loop. This avoids silently
misidentifying a syntactically accepted INP as a frame-accurate replay.
After readiness, an operator still needs to launch the matching emulator
on the private workstation, verify that the recording is being played
rather than user input being accepted, and measure frame-counter/video
alignment against observed Start events. Only then should reference PNGs
be collected according to the Stage271/272 capture plan.

## Receipt privacy and limits

The output is created exclusively, with private file permissions (0600),
outside the repository. It contains **only** scalar booleans, the original
record count and a coarse readiness status. It never copies the ROM, input
stream, executable output, local paths or screenshots. No screenshot
provenance, emulator binary hash attestation, input-to-video synchronization,
CPS-1/gameplay parity or physical Switch execution is claimed by this gate.
Banner checks can be spoofed: a green receipt is **not independent proof**
that a genuine historical WolfMAME executable ran.

The helper's two probing subprocesses are capped by timeouts and do not
run gameplay. For full trust, inspect the binary's provenance separately.

## ROM-free test

```sh
python3 -m unittest discover -s tests \
  -p 'test_wolfmame0106_private_binary_gate.py' -v
```

All test INP/WLF fixtures and fake CLI binaries are synthetic. No real
WolfMAME, ROM, recording, emulator screen or hardware is tested in CI.
This change is stacked on Draft PR #86 and does not alter `main`,
the original game files, or approved cover artwork.

# Stage284 — private MAME 0.106 MNG candidate frame audit

Stage283 successfully built ROM-free upstream **MAME 0.106** and verified that
the dino driver exists in its XML output. Stage284 adds an independent
validator for a **future private video capture** of the original game.

The original [MAME 0.106 src/png.c](https://github.com/mamedev/historic-mame/blob/mame0106/src/png.c)
uses this simple-MNG pattern:

    MNG signature; MHDR (28 bytes);
    [PNG IHDR ... IDAT ... IEND] for each frame; MEND

## Suggested private playback experiment

Run the actual historical executable on a **Windows workstation** with
the original, authorized dino.zip in a private ROM directory and the
original dino.inp in the emulator's private inp directory. Keep its
dino.wlf companion private. After confirming clean recording playback:

    mame0106.exe dino -playback dino -rompath C:\private\roms -frames_to_run 121 -mngwrite stage284

Here stage284 is a basename; the historical emulator uses its MNG
file handling paths. Determine the actual filename and output directory
from the tested build: **do not infer its location**. A public GitHub
Actions job must not receive the game data. A matching WolfMAME 0.106
executable remains preferable for recording fidelity; upstream MAME
0.106 is an experimental compatibility test, not WolfMAME attestation.

The number passed to -frames_to_run is the *requested run limit*, not
independent evidence that the same number of INP records or displayed
frames was consumed. -mngwrite can create video container bytes only
when an emulator can run and draw frames.

## Audit an MNG that actually exists

    python3 tools/wolfmame0106_private_mng_audit.py \
      --mng /private/captures/stage284.mng \
      --minimum-frames 2 \
      --out /private/audits/stage284-mng.json

The audit verifies signature; 28-byte MHDR, simplicity profile and
frame dimensions; every chunk CRC; no nested/truncated/extra chunks;
MEND; fully decoded 8-bit PNG IDAT streams and scanline filters;
actual candidate frame count; and pixel equality of adjacent frames
after PNG scanline filters are removed.

**Counts report decoded candidate frames, not INP frames or authenticated
gameplay.** Different PNG byte streams containing identical RGB pixels
do not count as motion. Different pixels cannot prove the images came
from the real emulator, that the original INP was followed, or that
video timing aligns to the INP event clock.

The report contains no ROM, input, original image pixels, private paths,
screenshot filenames or gameplay artwork. The JSON report is created
exclusively in a private directory with mode 0600. The source MNG is
never modified. The audit refuses symlinks and public repo destinations.
Input MNG limit: 512 MiB, 3,601 candidate frames.

## Synthetic CI

    python3 -m unittest discover -s tests -p 'test_wolfmame0106_private_mng_audit.py' -v

All 15 tests synthesize artificial 2×2 RGB images. No copyrighted
game content or private recording is committed to GitHub.

Draft PR is stacked on Stage283, without modifications to main,
approved artwork or original game assets.

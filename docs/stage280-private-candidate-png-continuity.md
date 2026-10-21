# Stage280 — private candidate PNG temporal-continuity audit

**Purpose:** Stage272 validates candidate screenshots' PNG containers, but
valid files can contain frozen duplicates, recompressed copies of a still or
wrong temporal ordering. Stage280 compares **decoded pixel channels** rather
than filenames, file hashes or compressed streams. This is a quality check,
**not** verification of original-game playback.

## Private capture prerequisites

1. Keep the original INP/WLF and ROM on the private workstation, not GitHub.
2. Apply Stage279's executable/ROM readiness gate. Green means only ready
   to attempt real playback, not provenance or frame alignment.
3. Use the actual compatible 0.106 emulator and verify that it is playing
   the original recording rather than accepting live controls. One historical
   0.106 Windows example is `mamep106-vc.exe dino -playback dino` with
   `dino.inp` in the emulator INP directory; exact behavior may vary.
   Prior configuration/NVRAM can cause desynchronization. Relevant historical
   discussion: https://www.classicarcadegaming.com/forums/index.php?topic=213.0
4. Capture exactly the images requested by the private Stage272 request,
   using the requested indices in the names, e.g. `frame-00000000.png`.
   A filename alone does not prove a matching video frame.

## Run

```sh
python3 tools/wolfmame0106_private_visual_continuity.py \
  --request /private/audits/bootstrap-frames.json \
  --captures /private/audits/screenshots \
  --out /private/audits/stage280-visual-continuity.json
```

The paths above are **placeholders**. No screenshots were generated or
retrieved for this code change.

The tool verifies exact filenames and set membership, PNG CRC and deflate
integrity, valid scanline filters and consistent dimensions. It undoes PNG
filter predictors and converts 8-bit RGB, RGBA, grayscale or indexed pixels
to RGBA8. Transparent indexed `tRNS` chunks and frames above 4 million
pixels are rejected rather than silently miscompared. Only pairs whose
**requested input indices differ by exactly one** are compared: no sparse
overview pair is mistaken for consecutive frames.

A private JSON report records counts of changed/unchanged adjacent pairs,
fraction of pixels changed, and first changed candidate pair. Identical
pictures recompressed with different PNG filters do not count as motion.
Two visually different frames can come from any source; static screens can
also be valid. The report always leaves these flags **false**:

- `emulator_provenance_verified`
- `actual_inp_playback_verified`
- `input_video_alignment_verified`
- `original_gameplay_parity_verified`
- `physical_switch_tested`

The report is created exclusively in a private directory with 0600
permissions, without PNG data, original button input, private paths or ROM
bytes. No commercial imagery is committed.

## Synthetic CI

```sh
python3 -m unittest discover -s tests \
  -p 'test_wolfmame0106_private_visual_continuity.py' -v
```

Stage280 is stacked on Draft PR #87. It does not modify original ROM,
approved covers, native gameplay physics, or `main`.

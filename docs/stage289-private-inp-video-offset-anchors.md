# Stage289 — private candidate INP/video offset annotations

Stage289 extends the Stage286–288 private capture chain with a **limited
manual-anchor timing experiment**. It does not claim that decoded frames have
already been recorded from the user's original game. It must run only on a
private workstation with authorized local original-game data.

## Why these checks matter

The Stage287 pixel-overlap test can show that two supplied MNG windows agree
at the **same requested MAME video callback indices**, but it does **not**
establish which INP record corresponds to a callback. Stage288 binds the
videos to the original candidate capture receipts; that still does not
authenticate the game or identify the input/video timing.

The updated Stage286 runner additionally computes SHA-256 for the **staged
INP and WLF files**, storing those two digests **only in the exclusive private
capture receipt**, alongside the previously added MNG fingerprint. The
Stage289 audit requires both capture receipts to bind to the *same* local
INP/WLF bytes and to pass the Stage288 video-pair check.

Use **new** Stage286 captures and receipts. Legacy capture receipts lack
the input and WLF fingerprints and are intentionally rejected.

## Human-observed anchors

In a *new private file* `C:\private\audits\response-anchors.json`, note
three or more widely separated, manually observed candidate visual responses.
The following JSON is merely an **artificial format example**. Its numerical
events are not verified observations of the original game:

```json
{
  "schema": "dino-private-mame0106-observed-response-anchors-v1",
  "anchors": [
    {
      "signal": "p1.attack_button1",
      "input_record_index": 36720,
      "video_callback_index": 36724
    },
    {
      "signal": "p1.jump_button2",
      "input_record_index": 36800,
      "video_callback_index": 36804
    },
    {
      "signal": "p1.attack_button1",
      "input_record_index": 37000,
      "video_callback_index": 37004
    }
  ]
}
```

Do not copy these invented example indices into a real experiment. The
`input_record_index` must point to an actual **unpressed-to-pressed input
transition** found in the private input stream. The
`video_callback_index` is the manually chosen callback frame containing
the *candidate* response. Start counters and the actual response delay may
differ; the tool does not verify the annotation's semantic correctness.
Use several distinctive events with at least 30 input records between
onsets; repeated combat motion can cause false correlations.

The index pair is not an established causal link. In particular, attack
animation, button debouncing, UI transitions or delayed effects might
legitimately add different latencies.

## Private command

Complete two Stage286 captures with partially overlapping windows as in
[Stage287](stage287-private-mng-window-overlap.md), and validate their MNG
pair as in [Stage288](stage288-private-capture-receipt-binding.md).

Then run **locally**, with the real private INP/WLF and annotations:

```bat
python tools\wolfmame0106_private_alignment_anchors.py ^
  --inp C:\private\recordings\dino.inp ^
  --wlf C:\private\recordings\dino.wlf ^
  --annotations C:\private\audits\response-anchors.json ^
  --first-mng C:\private\audits\window-a.mng ^
  --first-receipt C:\private\audits\window-a.json ^
  --second-mng C:\private\audits\window-b.mng ^
  --second-receipt C:\private\audits\window-b.json ^
  --min-overlap 16 ^
  --out C:\private\audits\stage289-offset-candidate.json
```

The script checks the original supplied INP/WLF format privately, ensures
both receipts contain those exact bytes' SHA-256 fingerprints, validates two
candidate MNG/receipt pairs and their dynamic overlap, then verifies each
annotated **input press edge** against the expected bit of the MAME 0.106
source-grounded dino input-port layout. A different WolfMAME fork's mapping
or actual input behavior remains unverified.

The reported offset is `video_callback_index - input_record_index`.
A candidate with three or more independently selected observations and an
offset spread of at most two callbacks is labelled:

`CONSISTENT_MANUALLY_ANNOTATED_OFFSET_HYPOTHESIS_ONLY`

This does **not** mean exact synchronization has been established; it means
only that the supplied annotations agree with the stored input-edge bits
under an assumed mapping. Spread above two becomes
`DISPERSED_MANUAL_OFFSETS_NOT_CALIBRATED`. Other invalid or private
evidence produces a blocked status and a nonzero exit code.

The exclusive private JSON output records only counts, median/range/spread
and explicit **false** provenance and alignment flags. No raw input events,
annotations, game images, recording paths or cryptographic fingerprints
are included in this derived output. Even the output should remain private
while the full experiment is unverified.

## CI and subsequent independent verification

Public CI exercises the checker only with synthetic 2x2 PNG/MNG frames,
artificial input rows, artificial metadata and artificial receipts:

```sh
python -m unittest discover -s tests -p 'test_wolfmame0106_private_alignment_anchors.py' -v
python -m unittest discover -s tests -p 'test_wolfmame0106_private_mng_capture.py' -v
```

To independently demonstrate real alignment in a later stage, use an
instrumented emulator with corresponding **per-frame input-record and video
callback counters in the same process**, and compare that tracing with the
privately observed response anchors. Neither the synthetic tests nor the
current manual annotations provide that attestation.

Keep ROM, INP, WLF, MNG, all annotations, private receipts, and original
captured frames **outside GitHub**. Physical Nintendo Switch gameplay is
also not established by this tool.

# Stage288 — private MNG capture receipt binding

Stage286 can now include a SHA-256 digest and byte count of the **candidate MNG
file** in its private exclusive JSON capture receipt, after MNG and PNG integrity
checks and exact frame-count validation. The MNG digest is **not** a hash of
the original ROM, INP or WLF and is never printed by the tool. Its purpose
is to detect an accidentally substituted or altered captured-video file
when comparing two Stage287 overlap windows.

These two fields contain **derived private video content metadata** and should
remain on the private workstation alongside the MNG files. Do not upload
the receipts, images, hashes or input files to public GitHub Actions.
The tool does not authenticate the recording's original provenance.

## Using two receipts

Create two **fresh** Stage286 MNG capture files using the procedure described
in [Stage287](stage287-private-mng-window-overlap.md). Each invocation must
include `--capture-out` and `--out` so the MNG and its private JSON receipt
are retained in separate, new private files.

The new comparator requires each MNG plus its corresponding receipt:

```bat
python tools\wolfmame0106_private_capture_receipt_pair.py ^
  --first-mng C:\private\audits\window-a.mng ^
  --first-receipt C:\private\audits\window-a.json ^
  --second-mng C:\private\audits\window-b.mng ^
  --second-receipt C:\private\audits\window-b.json ^
  --min-overlap 16 ^
  --out C:\private\audits\stage288-linked-overlap.json
```

This command, not the older Stage287 bare-MNG comparator, validates the
receipt/MNG pairs **before and after** decoding and comparing the overlap.
The check requires:

- Stage286 schema, confirmed preflight, valid MNG and PNG candidate,
  exact requested frame count and privately retained MNG;
- an emulator process that returned code 0 without timeout;
- internally consistent start/end positions, count and recording-length
  bounds, with frame indices supplied by each receipt (not by the user);
- a 64-character SHA-256 digest and precise file-byte count matching
  the current candidate MNG bytes;
- distinct MNG files and distinct receipt files.

Legacy Stage286 receipts without a video SHA-256 must be generated again with
the updated private runner; the comparator deliberately does not silently
accept them. Never rewrite a historical receipt and claim it came from a
successful real capture.

The final Stage288 receipt is an **exclusive private JSON file** containing
overlap status, aggregate counts, and boolean linkage checks. It never
contains source paths or content hashes. Its clean dynamic-match exit code
is 0; other results and invalid evidence return 2. A private receipt is
ordinary unsigned data and could itself be modified. A matching digest only
links the *supplied files*; it does not prove separate genuine emulator
runs, WolfMAME binary authenticity, original INP playback, input/video frame
alignment or physical Nintendo Switch execution.

## Public CI (synthetic)

```sh
python -m unittest discover -s tests -p 'test_wolfmame0106_private_capture_receipt_pair.py' -v
python -m unittest discover -s tests -p 'test_wolfmame0106_private_mng_capture.py' -v
```

Tests construct only artificial MNG containers and synthetic local receipts.
The public repository contains no original dino ROM, INP, WLF or MNG.

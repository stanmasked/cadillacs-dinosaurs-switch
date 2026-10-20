# Stage 263 — host X11 capture-call cadence (ROM-free)

Stage 262 requires the original four RGB values and the host-monotonic
XGetImage call start/end offsets for **every** actual post-host-command
sample from both native NRO modes.

Stage 263 adds a **read-only, strictly provenance-checked** audit that
reports the sum of rounded capture-call envelopes and the idle time
between consecutive calls. The arithmetic must telescope exactly:

`last_capture_end - first_capture_begin = sum(call widths) + sum(inter-call gaps)`

It also records the maximum observed inter-call gap and the gap between
the last counter-absent and first counter-present X11 capture calls.
Data comes from original guest artifact ZIPs and separately built NROs.
The mandatory Stage 262 paired verifier, guest runtime/audio mode
selection, NRO full SHA-256 and stored attestation are revalidated.
Any missing, malformed, reordered, overlapping, tampered or replayed
source evidence fails closed without generating a success file.

The values are **rounded microsecond host capture-call timing data**,
not measurements of the exact first appearance of a visible frame.
Screen updates may happen between calls **or during** XGetImage.
These metrics do not prove causal differences between separately
scheduled baseline and extra-poll runs, actual guest HID delivery,
physical Joy-Con actions, Switch LCD photon timing, GPU scanout or
audible speaker latency. The output deliberately keeps all such
claims false.

This does not modify game logic, normal demo/replay, NRO byte content,
source ROMs, screenshots, or approved artwork. Keep PR stacked Draft;
do not merge into main without explicit review.

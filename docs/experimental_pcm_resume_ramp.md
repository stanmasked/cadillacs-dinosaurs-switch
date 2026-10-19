# Optional post-drop PCM resume ramp (stage 220)

This is an **experimental ROM-free selftest feature**, not a production
audio change or a claim of better audible output. The goal is to evaluate
one possible source of clicks after a 60-Hz PCM block is discarded by
the fixed two-page audout queue.

## Behavior under an explicit selftest-only compile opt-in

The flag `DINO_AUDIO_EXPERIMENT_RESUME_RAMP` is honored **only** when
`DINO_EMULATOR_SELFTEST` is also defined. Neither flag combination is
enabled in the normal Nintendo Switch build or either current baseline /
extra-poll NeXium guest build.

When an active audio queue is full and a 60-Hz PCM block is discarded,
the selftest adapter records a one-shot marker. At the next successful
buffer admission, the synth has already generated its usual 800 signed
16-bit stereo PCM frames, and the normal `dino_pcm_witness_feed()` hash
has already seen **unmodified** samples. A pure integer, in-place
output-only ramp then scales the first **96 stereo frames** (2 ms at
48 kHz) with exactly `(frame_index + 1)/96`; the remaining 704 frames
are byte-identical. The marker clears, and there is no effect on further
ticks unless another full-queue skip happens.

The ramp neither resubmits stale PCM nor modifies the queue's depth,
libnx `audout` polling cadence, game timer, catch-up steps, input, ROM
assets, latency compensation, or the synthesis state. It adds no frames
of output. Cache flush remains after the optional sample transformation.

## Verification and decisions

`tests/test_dino_pcm_resume_ramp.py` builds the pure C module with
GCC `-std=c11 -Wall -Wextra -Werror`, independently checks full-scale
positive/negative samples and both interleaved channels, rejects bad
arguments without mutating input, checks determinism and the opt-in
compile guards, and proves the generated-PCM witness is fed before
optional output-only shaping.

Normal CI builds run these tests without enabling the feature.
Testing the feature on a physical Switch, inspecting sound output or
making a quality decision requires a future **separately selected**
selftest. No actual speaker improvement, latency, or audible click
reduction is asserted. Original arcade ROM/audio samples are neither
necessary nor stored in this branch.

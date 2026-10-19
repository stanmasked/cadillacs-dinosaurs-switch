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

The pending transition is represented by the portable
`DinoPcmResumeRampState` state machine: repeated queue-full drops coalesce
into one pending attack, and the first subsequent **successful** admission
consumes it exactly once. An invalid buffer does not consume pending state.
The state resets with the adapter's audio lifecycle. The number of
applications is a saturating diagnostic counter, not a quality metric.

The ramp neither resubmits stale PCM nor modifies the queue's depth,
libnx `audout` polling cadence, game timer, catch-up steps, input, ROM
assets, latency compensation, or the synthesis state. It adds no frames
of output. Cache flush remains after the optional sample transformation.

## Sample-level tradeoff: no guaranteed click improvement

A new ROM-free benchmark at
`tools/dino_pcm_resume_edge_benchmark.py` compiles the **actual C**
ramp as a native shared library, creates only invented 800-frame
signed-int16 stereo signals, and compares the immediately previous
sample with the first admitted sample before and after shaping.

For a two-channel constant `(30000,-24000)` admitted block:

- If the preceding stereo frame is **silence** `(0,0)`, the maximum
  immediate signed-sample jump falls from **30000** to **312**.
- If the preceding frame already equals the admitted block's first
  sample `(30000,-24000)`, the unmodified boundary is already
  **continuous (jump 0)**. The ramp creates a jump of **29688**.
- If the preceding frame is `(-30000,24000)`, the original jump
  is **60000**, versus **30312** after shaping.
- True digital silence stays exactly zero. Both channels' samples
  after the first 96 frames are *identical* to the original.

The benchmark also computes maximum within-ramp differences,
per-sample squared distortion, exact integer reference agreement and
output frame conservation, storing the outcomes in a machine-readable
JSON report. **Sample jump magnitude is only a mathematical proxy.**
It is not a psychoacoustic click score, an output waveform captured
from the guest, physical Switch audio, or a speaker latency measure.

**Decision: keep the existing ramp experimental and OFF by default.**
The negative control demonstrates that a blindly applied restart ramp
can damage an already continuous edge. Before any production opt-in,
a separate actual-output comparison and safety evaluation would be
required. This synthetic analysis does not justify activating it.

## Proposed fail-closed sample-step gate (stage 223)

The **guarded proxy remains an offline diagnostic**, not a game feature.
The portable code and header reside in
`tools/native/dino_pcm_resume_guarded_proxy.[ch]`, explicitly **outside**
the Makefile's automatic `source/*.c` compilation. Nothing in
`source/dino_switch_sound.c` calls this gate, so neither the standard
Switch NRO nor the original opt-in ramp NRO acquires it.

Given a supplied two-channel final PCM sample from the **previously
submitted** block and the next generated 800-frame block, the pure
integer C routine compares two candidate trajectories over the
boundary and the first 96 frames:

- Original (unmodified) 16-bit stereo PCM.
- The existing 96-frame fixed-point ramp on the same block.

It recommends the ramp **only** if its greatest absolute adjacent
sample difference does not worsen in **either** channel and improves
strictly in the combined worst channel. It rejects NULL previous
samples, invalid input, silent/no-benefit cases, an already continuous
signal and any case where just one stereo channel becomes worse.

There is a fundamental observability limitation: the last sample of a
*submitted* block is **not** necessarily the last sample actually
*played* by libnx audout. Pending audio pages and host output latency
are not controlled by this analysis. The gate is a mathematical
sample-difference proxy, not a validated way to avoid audible clicks.
Even when the maximum difference decreases, some smaller local
differences could still increase and listeners may perceive audio
differently. The gate must stay disconnected from the actual guest
adapter until separate timestamp/played-waveform evidence exists.

`tools/dino_pcm_resume_guarded_proxy_report.py` exercises the
**actual GCC-compiled C gate and ramp**, checks a separate Python
oracle and reports positive and negative cases, including a mixed
stereo case where only one channel would worsen. It does not access
game audio, hardware samples, private ROMs, firmware or console keys.

**Decision: fixed and guarded restart ramps both stay disabled by
default.** A mathematically nonworsening artificial sample-step
criterion is not proof of improved speaker output.

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

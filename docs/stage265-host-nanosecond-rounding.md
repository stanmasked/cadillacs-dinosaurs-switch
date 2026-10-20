# Stage 265 — nanosecond-phase validation of rounded X11 host gap

Stage 264 computes a conservative host-only interval from the
`xdotool keydown` subprocess completion to the first subsequent
`XGetImage` **call start**, using already-existing host monotonic
clock offsets represented only in integer microseconds.

Stage 265 isolates the three-value rounding calculation into a strict
pure function and checks all **1,000 nanosecond completion phases**
against eleven exact synthetic post-completion delays. A second
independent set checks nonzero clock origin, varying command call
duration and gap size. These are only *mathematical synthetic tests*;
they cannot be cited as new real NeXium samples.

For `S = floor(sample_start_ns/1000)`,
`L = floor(command_complete_ns/1000)`,
`U = ceil(command_complete_ns/1000)`, all relative to the same
command invocation origin, the saved host timing is compatible with
the conservative interval:

`max(0, S-U) <= actual_no_capture_us <= S+1-L`

The auditor rejects negative, non-integer, Boolean, reversed,
unbounded or noncanonical floor/ceil offsets. Source provenances,
Stage 262–264 mandatory NeXium checks, NRO identities, artifact
schema and game build stay unchanged. The synthetic oracle covers
rounding correctness, not a new physical end-to-end observation.

There is still **NO claim** of first visual onset, physical
controller-to-LCD latency, synchronized guest input timestamps,
GPU scanout, speaker audio or a causal baseline/extra-poll
performance comparison. Do not merge stacked Draft PR into main
without review.

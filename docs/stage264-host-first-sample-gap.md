# Stage 264 — first post-keydown X11 blind interval

The previous Stage 263 verifier audited the intervals **between** all
post-command X11 `XGetImage` calls. It did not independently report
the period when no X11 image was captured **after** the `xdotool`
keydown subprocess returned and **before** the first post-command call.

The new paired audit recomputes two existing mandatory source chains:
Stage 263 complete four-RGB capture series and Stage 258 host command
brackets. It requires both saved raw-source attestations, distinct
NRO SHA-256 values, actual guest frame token equality, monotonic time
ordering and the same final X11 image across the two chains.

If the first X11 call's host command-relative start offset, rounded
down in microseconds, is `S`, and the command completion offset has
floor `L` and ceil `U`, the honest **conservative** blind interval is:

- Lower: `max(0, S - U)` microseconds
- Upper: `S + 1 - L` microseconds

This bounds time from **successful host subprocess completion** to
the **beginning of first X11 sample capture**, not input-to-display
delay. Even if the X11 counter first appears in a later sample, onset
can happen between or during samples. Nor does the calculation prove
physical Joy-Con timing, native libnx guest input receipt, GPU scanout,
LCD photons or causality across separately scheduled audio modes.

No game code, Switch NRO build recipe, original ROM bytes, art or
approved cover layouts are modified. The check is mandatory in PR CI,
but the PR remains stacked and Draft pending validation and review.

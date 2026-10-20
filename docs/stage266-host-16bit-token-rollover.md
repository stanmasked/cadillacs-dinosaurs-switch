# Stage 266 — host 16-bit token rollover safety

A real guest render iteration is a full 32-bit integer. The compact
X11 frame-token pixels represent only `iteration & 0xffff`. Stage
253 already checks the original native token trace, finds **one**
unique native submission for that observed 16-bit token, and checks
its full-NRO SHA-256 and selected audio mode.

Stages 261/262 were incorrectly using the token as the *full*
`guest_submitted_render_iteration`, which is indistinguishable for
the earlier verified guest examples around iteration 2,500–3,500.
This can falsely reject a genuine longer run after iteration 65,535.

Stage 266 now carries forward the authentic full-width iteration from
the previous Stage 259 native-NRO-bound verification, checks that the
host 16-bit token equals the low 16 bits, and preserves the same
full-width iteration comparison in Stage 264 while comparing the
X11 value modulo 65,536. Two independent chains still must agree;
one 16-bit token cannot identify a frame in isolation, and no
ambiguously repeated token is accepted upstream.

Eleven regression cases cover unwrapped frames, the first and second
65,536-frame wrap, incorrect low token, a mismatched full frame
with **identical low bits**, unacceptable native iteration values and
a forged positive X11 token. Synthetic mocks change only the prior
verifier's *returned* native iteration, not the real ROM, NRO or
saved source evidence; they are explicitly not new NeXium captures.

This does not alter gameplay, guest render timing, event generation,
physical input latency, guest-to-host clock synchronization or LCD
scanout. The Stage 264/265 bounds and attestations keep their own
host-only observational meaning.

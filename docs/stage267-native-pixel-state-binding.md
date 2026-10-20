# Stage 267 — native submitted framebuffer state binding

Stage 253 validates the real guest frame-token trace and a separately
guest-written one-row framebuffer CSV. In both sources the native game
writes frame ID, arena tick, feedback TTL and impact TTL during the
**same submitted frame**. The original verifier compared frame ID
and tick but did not require that the guest pixel CSV's two effect
state values match the corresponding full-width trace row.

The verifier now validates canonical integer `feedback_ttl` and
`impact_ttl` in the pixel CSV and demands both match the trace
record at its full-width `render_iteration`, alongside the already
required arena tick. It also continues to require the exact NRO hash,
the unique encoded 16-bit X11 token within the native trace and
genuine four-color guest framebuffer pixel values.

The guest framebuffer CSV represents the **first sampled native
counter frame**; the X11 host image may contain a **later** submitted
frame. Therefore they must not be forced to have the same full-width
frame ID. They must both be independently identified in the native
trace. Stage 267 deliberately preserves this distinction.

Fourteen synthetic regression tests cover first/second 16-bit wraps,
exact 65535→65536 zero-token boundary and ambiguous repeated zero-token rejection after wrap, correctly accepting a later
host-visible X11 frame, forged TTL/impact values in either native
witness and noncanonical integer strings. These are synthetic
interface tests, *not* a new 65k-frame real NeXium execution.

No game engine, native NRO source, emulator binary, original ROM,
approved cover, sound or framebuffer capture protocol is changed.
The checks are strict enough to fail closed on inconsistencies and
never represent host X11 sampling as physical display latency.

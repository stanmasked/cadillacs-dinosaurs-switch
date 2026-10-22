# Stage324 — bounded private NeXium process-tree cleanup

The pinned Stage318 launcher now gives the private Stage316 runner a 220-second
outer deadline. This is deliberately longer than the shell runner's own
190-second guard, leaving time for orderly shutdown instead of cutting the
run off early.

The launcher starts the shell harness in a new session. On normal exit or
timeout, it terminates the runner process group and enumerates the runner's
current Linux proc descendants, so a NeXium process that created its own
session cannot be silently left behind if the outer timeout fires. Spawn and
timeout failures remain redacted; no private argv, source paths, console logs,
ROM bytes, graphics, screenshots, or guest traces are emitted.

Public regression tests use mocked process objects and invented paths only.
They verify timeout alignment, descendant and process-group termination,
success-path cleanup, and redaction of launch errors. They do not run NeXium,
load a ROM, or assert original-gameplay or input-recording playback.

The Stage323 local optical result remains limited to 14 synthetic scene states
rendered from source-verified CPS-1 graphics. It is not proof of authentic
arcade gameplay, dino.inp/dino.wlf replay, or physical Nintendo Switch output.

# Stage325 — bounded private MAME probe process groups

The Stage279 private MAME readiness probe previously killed only the direct
emulator PID on timeout. A probe executable can launch a helper and leave it
running after the parent is stopped, so a timeout was not a complete cleanup
boundary.

The probe now starts in a dedicated session and always cleans its process
group after the command returns or times out. This covers both the normal
readiness path and the timeout path while keeping stdout/stderr captured in a
temporary file and redacting all raw output. A failed or timed-out probe still
cannot produce a ready receipt.

New tests use tiny synthetic shell scripts that spawn a child sleep process.
They verify that the child is stopped both when the parent times out and when
the parent exits successfully. No MAME binary, ROM, INP/WLF recording, game
graphics, screenshot, or private receipt is used or uploaded.

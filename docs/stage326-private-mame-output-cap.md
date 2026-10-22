# Stage326 — strict memory-bounded MAME probe output

The private MAME readiness probe previously wrote the complete emulator output
to a temporary file and checked its size only after the process exited. That
redacted the report but did not actually bound disk usage.

The probe now streams output from a pipe, retains at most MAX_OUTPUT plus one
byte in memory, and drains/discards any excess so the child cannot block on a
full pipe. If the process exceeds its deadline, the existing Stage325 process
group cleanup remains responsible for terminating the probe and its helpers.
An oversized output produces an empty, redacted result and cannot be treated
as a ready receipt.

The new public tests use synthetic shell scripts, patch the cap to 16 bytes,
and forbid temporary-file spooling. They verify that oversized output is
discarded and small output is returned normally. No MAME binary, ROM, INP/WLF
recording, graphics, screenshot, or private receipt is used or uploaded.

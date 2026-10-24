# Stage367 — independent Windows PowerShell synthetic execution gate

Stage366's owner-only Windows verification capsule exists, but Windows MAME
`-verifyroms dino` with private ROM has **not** been executed. The previous
PowerShell runner trusted SHA-256 pins drawn solely from `capsule.json`: a
self-consistent substitution of a fake executable, fake ROM and manifest could
appear successful. Stage367 explicitly hard-pins the known executable, private
ROM and historical driver XML SHA-256 in the **production PowerShell script**.
The owner must still verify the *outer ZIP* hash before extracting: a script is
not a cryptographic signature of itself.

Stage367 adds a dedicated GitHub Windows-2022 job that uses **only** C# stub
source, synthetic text (not a real ROM or even an actual ZIP), and synthetic
configuration. The real production script stays untouched in source, and its
`GITHUB_ACTIONS` refusal is first executed without any files present.
Separately, a disposable fixture copy replaces the three source pins with
freshly generated synthetic SHA-256 values, removes the public-runner guard
**only inside that temporary fixture**, and renames the success marker to
`status=synthetic_runner_branch_only` to avoid mistaken historical verification
claims in public logs. A compiled C# stub emits positive and adversarial text
without ever parsing original game content. It verifies that the actual
Windows PowerShell 5.1 subprocess path:

- requires both exact positive lines and exit code 0;
- rejects missing summary, extra negative lines, nonzero exit and stderr-only
  fake output;
- rejects oversized emulator output and modified synthetic files;
- rejects a forged capsule manifest, despite its otherwise coherent structure;
- refuses public Actions invocation of the **unmodified** production script.

The job produces no uploaded artifact and prints only a synthetic aggregate.
No real `mame0106.exe`, original `dino.zip`, input recording, screenshots,
graphics, or raw emulator logs are present in public CI. This is a test of
Windows PowerShell behavior only, **not** execution of MAME or ROM validation.

For the owner-held private capsule, the Stage367 runner change requires a
**new versioned private ZIP**. The older Stage366 ZIP is retained unmodified as
an earlier reference; do not overwrite or relabel either original. Both the
Stage367 ZIP and detailed manifest belong exclusively in owner-only Google
Drive, with owner-only permissions and SHA-256 reread after upload.

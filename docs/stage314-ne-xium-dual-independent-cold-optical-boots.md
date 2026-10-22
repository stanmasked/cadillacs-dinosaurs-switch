# Stage314 — two independent NeXium cold boots for synthetic 14-scene optical playback

Stage313's pinned real NeXium guest run succeeded on the full artificial
14-scene sequence, with fourteen matching host-visible optical IDs and
**at least 24/25 independent scene pixel samples per X11 capture**.

A single successful run leaves cold-start reproducibility untested.
Stage314 runs **two separate Linux GitHub Actions jobs** (trials `a` and
`b`) using the *same SHA-256-attested opt-in Switch NRO* but with:

- A fresh, independent GitHub runner for each trial
- A newly created private ROM-free Stage307/308 SD tree, outside the source
- A fresh isolated NeXium home/config/cache and `NEXIUM_DATA_ROOT`
- A new NeXium guest process started in Xvfb/software-Vulkan
- Fourteen actual guest `FRAME_SUBMITTED` events and fourteen separate
  host X11 optical frame/image-sample proofs **per trial**

This is not a host-only mock repeat. The two matrix jobs each independently
invoke the real pinned NeXium binary, generate stage-310 fake binary assets,
and execute the opt-in NRO. The fail-fast setting is disabled so failure
of one trial does not conceal the other's result.

The final comparator `tools/verify_nexium_optical_cold_repeat_314.py`
receives exactly two distinct summaries produced by those jobs. It refuses
one missing result, symlinks, identical input paths, incomplete frames,
optical identity discrepancies, graphics with too few matched sample
points, or any broadened claim about original arcade data or physical
Nintendo Switch hardware. Mock unit tests exercise rejection behavior
but **never** count as guest evidence.

Only bounded status JSON is uploaded, not ROMs, keys, firmware, synthetic
graphics binaries, real X11 screenshots, host windows, raw guest CSV,
machine-specific filesystem paths or emulator logs.

## Workflow and interpretation

`.github/workflows/cps1-optical-cold-repeat-314.yml` builds the NRO once,
runs the two independent NeXium jobs and merges only the aggregate proof
objects into `stage314-two-cold-boot-summary.json`.

A passed final comparison means at least **28 genuine guest-submitted and
28 independently verified host-visible artificial scene frames** across
two isolated cold boots. It does not prove original Cadillacs and Dinosaurs
gameplay, historical WolfMAME 0.106 INP/WLF replay, screenshot distribution
rights, physical Switch scanout, arcade-specific controller timing or
audio fidelity.

Keep Draft stacked on Stage313 until the whole CI workflow is green;
do not merge into `main` without explicit authorization.

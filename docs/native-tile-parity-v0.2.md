# v0.2 Native CPS-1 tile rendering verification — 2026-10-16

## Build artifacts

- Native Switch NRO built successfully in the devkitPro CI container:
  [Actions #38930953403](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/38930953403)
- Python tests + standalone portable C tile decoder:
  [Actions #38930953449](https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/38930953449)
- **80 Python tests passed** on that CI revision; the C native decoder host-test binary also ran successfully.
- The NRO artifact is `cadillacs-dinosaurs-switch.nro`, 243,909 bytes, with `NRO0` at header offset `0x10` and SHA-256 `1d68e62cdf8ebd9c0a28ddcfaf5a51da37a7c4c302caa29cbb0c2deecb7a2862`.

## Reference tile decoding on private World 930201 source

The user-provided original ROM was assembled **locally** to a 4,194,304-byte graphics region with SHA-256:

`68786de27105ccc64f28f66ad1025f2e6f521aa60ab35c489fb0baaaa8679de1`

The equivalent standalone C decoder implementation (compiled by host GCC) was compared against the established Python reference on **1,034 selected actual ROM tile codes**, including bank/page boundaries and 1,024 deterministic pseudorandom codes:

- Pixels checked: **264,704**
- Mismatched pixel indices: **0**
- Out-of-range tile code rejected: yes

The repository also includes `tests/test_native_python_parity.py` for a separate **ROM-free synthetic** cross-language regression check. No ROM content, decoded pixel data, or derived graphics resources are committed.

## Scope / caveats

This means the same tile decoding algorithm is correct across two independent language implementations for sampled original data. It does **not** prove color palette fidelity, complete scene composition, sprite sequencing, actual Nintendo Switch hardware operation, or playable game logic.

The native homebrew reads a local graphics file from:

`sdmc:/switch/cadillacs-dinosaurs-switch/gfx.bin`

Read [Switch tile inspector setup](switch-tile-inspector.md). The only publicly committed application and tests are **ROM-free**.

# Stage335–337 — Wine32 smoke test and private replay handoff

## Stage335 — confirmed ROM-free MAME execution

The Wine32 offline runtime workflow completed successfully on revision
`dfe0e00b40450fd41ee453be3d2d47665065bdb3`:

https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39950979642

The job initialized a fresh 32-bit Wine prefix and launched the pinned
MAME 0.106 executable. The `-help`, `-showconfig`, and `-listxml`
probes all passed; the runtime metadata contained the expected
`mngcounttrace` setting and the `dino` driver. The MAME artifact
checksum and its eight-file manifest were verified before execution.

This workflow is deliberately ROM-free: no original ROM, INP, WLF,
MNG, or per-frame trace was present in the job or its artifacts.
The public ROM-free privacy gate, Python suite, and Nintendo Switch
bootstrap also passed on the same revision; Python CI reported 2,231
tests passed and one expected skip.

## Private ROM normalization — local result

The original archive was re-read from the user's private Drive folder.
The source-pinned MAME 0.106 driver manifest uniquely matched all 16
expected ROM entries against 28 source archive entries using size,
CRC-32, and SHA-1. A normalized `dino.zip` was created outside the
repository with mode 0600; each output entry was re-read and checked
against the manifest. The source archive was not modified. Neither
archive nor its contents were uploaded to GitHub.

This is an independent local integrity and filename-normalization check,
not the result of MAME's own `-verifyroms dino` command.

## Stage336 — current execution limitation

The current assistant-side Linux container has no native i386 ELF
execution support. The downloaded Wine32 packages and pinned MAME
artifact passed their checksum checks, and the Wine32 version probe ran
under QEMU user emulation, but launching the full Wine/MAME process
requires child-loader execution that this container cannot complete.
The attempt was stopped; no MAME ROM verification, playback, MNG, or
CSV trace is claimed from that local attempt.

Do not route private ROM/INP/WLF data through the public GitHub Actions
workflow. The remaining end-to-end check must run on a compatible private Linux
x86_64 host with native i386 execution support and Wine32, or a dedicated
VM that provides those capabilities. This runbook's wrapper is a POSIX
shell script and is not a native Windows launcher; a Windows-only host
needs a separate native adapter and is not covered by these instructions.

## Stage337 — external wrapper for the existing private capture runner

`tools/wolfmame0106_private_wine_external_wrapper.sh` is a small adapter
that forwards arguments to the guarded repository launcher. Copy it to
a new executable file in a private directory outside the checkout. The
wrapper intentionally refuses relative, missing, or symlinked launcher
paths. The repository launcher continues to enforce that the MAME
executable and Wine prefix are outside the repository.

On a compatible private Linux host, set the following environment variables
to local paths (never place them in a public workflow input or log):

- `REPO_WINE_LAUNCHER`: absolute path to
  `tools/wolfmame0106_private_wine_launcher.sh` in the checkout.
- `MAME0106_EXE`: absolute path to the checksum-verified MAME 0.106 executable.
- `WINEPREFIX`: private Wine prefix outside the checkout.
- `WINE_BIN`: the host's Wine command, normally `wine`.

Then run the bounded private capture runner:

```sh
python3 tools/wolfmame0106_private_mng_capture.py \\
  --emulator /private/cadillacs/wolfmame-wrapper.sh \\
  --rom-dir /private/cadillacs/roms \\
  --inp /private/cadillacs/recordings/dino.inp \\
  --wlf /private/cadillacs/recordings/dino.wlf \\
  --frames 121 --start-frame 0 --seconds 180 \\
  --capture-out /private/cadillacs/audits/stage337-first121.mng \\
  --trace-out /private/cadillacs/audits/stage337-counts.csv \\
  --out /private/cadillacs/audits/stage337-receipt.json
```

These paths are examples; replace them with actual private paths.
The runner first checks MAME 0.106 and `-verifyroms dino`. If either
preflight fails, it does not start playback. A structurally valid MNG
is still only candidate capture evidence: the receipt does not claim
input/video alignment, original-game parity, or Switch hardware success.

The wrapper's five synthetic tests cover argument forwarding and
fail-closed handling of unset, relative, missing, and symlinked launchers.
They do not execute MAME and do not use any real ROM or recording data.


## Stage338 — host support clarification and CI results

The new wrapper and its five synthetic tests passed the full repository
Python workflow on revision `d7018cc576eab72f846facdd0b7cce089040e1a7`:
https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39956626051

The run executed 2,236 unit tests successfully and preserved the code-only
scene-parity artifact. The public privacy gate also passed on the same
revision:
https://github.com/stanmasked/cadillacs-dinosaurs-switch/actions/runs/39956618817

The private local runtime probe verified the MAME executable against the
expected package SHA-256, and the QEMU-assisted Wine32 `--version` probe
returned Wine 10.0. However, invoking MAME `-help` still exits before the
MAME banner with `wine: could not exec the wine loader`. This is the
known child-loader limitation of this container's QEMU-user environment.
No MAME ROM verification, INP playback, MNG, or counter trace was produced.
Do not interpret the Wine version probe as MAME execution.

Therefore the next required gate is explicitly a compatible private Linux
host with native i386 process execution (or an equivalent VM). On that
host, run the guarded preflight, verify the `dino` ROM set, and only then
attempt the bounded 121-frame capture. Keep original ROM, INP/WLF, MNG,
CSV traces, and receipts out of public CI and the repository.

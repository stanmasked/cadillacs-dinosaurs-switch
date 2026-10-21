# Stage281 — bounded private launch attempt for WolfMAME 0.106

Stage280 can check pixel continuity of candidate screenshots but **has no
verified WolfMAME video**. Stage281 introduces an optional local-only
subprocess runner for trying the actual historical INP in a controlled
temporary workspace. It is **not** a completed original-game replay, and
does not capture frames.

## Environment and invocation

The real WolfMAME 0.106 command-line build, compatible authorized `dino`
ROM set, and the original paired `dino.inp` / `dino.wlf` must all be
present **outside this public Git repository** on the private host.

Historical WolfMAME 0.106 playback can use the **basename without .inp**
from its `inp` directory:

```text
mamep106-vc.exe dino -playback dino
```

Some later MAME versions and batch helpers differ. Do not accidentally
specify `dino.inp` to a 0.106 build that appends the suffix internally:
it can search for `dino.inp.inp`. Historical notes:
https://www.classicarcadegaming.com/forums/index.php?topic=213.0
and https://forum.arcadecontrols.com/index.php?topic=82834.0

The Stage281 runner always uses:

```text
<private-emulator> dino -playback dino -rompath <private-ROM-directory>
```

It first applies the Stage279 `-help` and `-verifyroms` preflight, plus
the independent Stage270 INP/WLF structural check. It then creates a private
temporary working directory with an `inp/` subfolder containing **byte-
identical temporary copies** named `dino.inp` and `dino.wlf`, along with
empty `cfg`, `nvram`, `diff` and `hi` subfolders. The original
files remain unchanged. The temp directory is removed when the session
ends, including on nonzero exits and timeouts. Files are limited to 128
MiB INP / 1 MiB WLF and written with private permissions.

The process runs for an explicit bounded observation window. Its raw
stdout/stderr are discarded to avoid accidental export of private paths,
config and recorded data. A timeout terminates the process (and its
process group on POSIX). The process result includes only a sanitized
exit code / timed-out bit. The default time limit is **10 seconds**;
that is only a startup smoke check, not the complete ~87-minute game run.

## Run locally — not in public GitHub Actions

```sh
python3 tools/wolfmame0106_private_playback_attempt.py \
  --emulator /private/wolfmame/mamep106 \
  --rom-dir /private/roms \
  --inp /private/recordings/dino.inp \
  --wlf /private/recordings/dino.wlf \
  --seconds 15 \
  --out /private/audits/stage281-replay-launch.json
```

These are placeholder paths. The private ROM and legacy executable
**must actually exist**; none is downloaded or created by this script.

If a historical Windows-only build cannot execute on the host, run this
on a compatible private Windows environment. A MAME 0.289 emulator is
**not** an interchangeable replacement for 0.106-format INP playback.
The old 0.106 executable may consult settings outside the temporary
working directory; a clean workspace does not independently prove
equivalent original DIP switches, controller settings or NVRAM state.

## What the result means (and does not mean)

- `PLAYBACK_PROCESS_EXIT_ZERO_UNVERIFIED`: the binary returned code zero.
- `PLAYBACK_PROCESS_TIME_LIMIT_UNVERIFIED`: a process was alive at the
  observation limit; it was terminated.
- `PLAYBACK_PROCESS_EXIT_NONZERO_UNVERIFIED`: the process exited with an
  error code.
- `BLOCKED_...`: the binary, ROM, input pairing or private staging
  failed before a meaningful launch.

**None** proves authentic input playback, rendered frames, completion,
timing alignment, an original-game gameplay match, or real Switch
hardware operation. These claims remain explicitly `false` in the JSON.
A malicious executable could simulate the command-line probes; separate
provenance checks are essential. Real proof still requires independently
observed emulator video frame IDs, an input-responsive Start transition,
and bound capture evidence using the earlier Stage272/280 tools.

The private result is created exclusively outside the repo with mode
0600 and never contains original recording bytes, ROM data, image pixels,
binary output or private paths.

## Synthetic CI

```sh
python3 -m unittest discover -s tests \
  -p 'test_wolfmame0106_private_playback_attempt.py' -v
```

All emulator executables in these tests are **fake shell programs**,
not actual MAME. The test INP/WLF are generated from artificial headers
and repeated byte values. The 15 tests cover traditional `-playback`
invocation, temporary copy equality, exit status, timeout, constraints,
privacy, symlinks, input mismatch and conservative evidence flags.

This is a Draft change stacked on Stage280 (PR #88), not a modification
to `main`, original assets or approved artwork.

# Stage370 — historical MAME 0.106 `dino -verifyroms` protocol contract

**Scope:** Static examination of the ROM-free, pinned public historical source
(`mamedev/historic-mame`, tag `mame0106`) and the Stage369 production
PowerShell script. This is **not** game execution and uses no original ROM,
input recording, graphic tile, private log, or actual gameplay frame.

The source-only tool `tools/mame0106_private_source_protocol.py` checks a
locally held upstream source ZIP by exact SHA-256, and independently compares
the three pinned upstream files `src/windows/fronthlp.c`,
`src/windows/config.c`, and `src/windows/fileio.c` against hard-pinned hashes.
Only then does it test the expected launch/output contract:

- The historical front-end defines `verifyroms` with `VERIFY_ROMS`.
- `rompath` is a string option and `readconfig` is a boolean option.
- A verified nonclone's correct set is printed as `romset dino is good`.
- The success summary is `1 romsets found, 1 were OK.`
- The front-end returns `0` when no incorrect sets exist; returns `2` for
  incorrect sets and `1` when no applicable set is found.
- Per-set results and summary go to stdout, while progress percentages go to
  stderr; the Stage369 script parses **stdout only** and checks process exit.
- Stage369 still requires both exact dino success markers, a zero exit code,
  no negative keywords, a local private Windows host, and the strict pinned
  original MAME executable and owner-held ROM SHA-256 values.

The checker refuses public GitHub Actions production use even though the
historic source itself is public; only **wholly synthetic** unittest fixtures
run on CI. It emits a fixed status and aggregate check count. Privately used
source filenames, raw source contents, input paths and diagnostic errors are
not exposed via output. Production checks use the exact *original* source ZIP,
not an unpinned or rewritten excerpt.

A passing static source protocol check improves confidence that Stage369's
PowerShell success criteria correspond to MAME 0.106's original CLI. It does
not establish that Windows host execution succeeded, that `dino.zip` passed
`-verifyroms`, that WolfMAME 0.106 can replay `dino.inp`, or that gameplay
screenshots are authentic. The later runtime evidence MUST be obtained
independently inside the owner-controlled environment, with all resulting
reports kept in the owner-only Google Drive archive (not GitHub artifacts).

For an owner-local repeat with a vetted, source-pinned historic ZIP:

```sh
python -m tools.mame0106_private_source_protocol --source-zip <OWNER_LOCAL_PINNED_HISTORICAL_SOURCE_ZIP>
```

The synthetic Python test module is
`tests/test_mame0106_private_source_protocol.py` (no real source ZIP or ROM).

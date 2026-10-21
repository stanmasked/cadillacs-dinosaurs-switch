# Stage282 — private original MAME 0.106 ROM filename compatibility

## Why this matters

The **exact original historical MAME 0.106 source**, tagged `mame0106`
in `mamedev/historic-mame`, lists 16 ROM data entries for the parent
`ROM_START( dino )` game in `src/drivers/cps1.c`:

https://github.com/mamedev/historic-mame/blob/mame0106/src/drivers/cps1.c

The user's independently held 28-file modern-style archive contains
**all 16 expected payloads** with matching 32-bit CRC, exact byte size and
SHA-1. The required 16 original data records differ mostly by *filenames*,
not bytes. Examples:

| MAME 0.106 expected name | Matching modern archive name |
|---|---|
| `cde_23a.rom` | `cde_23a.8f` |
| `cd_gfx01.rom` | `cd-1m.3a` |
| `cd_q.rom` | `cd_q.5k` |
| `cd_q1.rom` | `cd-q1.1k` |

**This is a file-format compatibility finding, not a claim of successful
emulation.** It was checked against original 0.106 *MAME source code*,
not against an executable WolfMAME playback or a frame capture.

A newer-era auxiliary `ioc1.ic1` PLD sometimes has different old/new
dumps (`a399772d` versus `0d182081`). It is *not among the 16
game data ROMs referenced by the MAME 0.106 dino driver*, and the tool
intentionally ignores such newer, auxiliary records. No patching of
the content is performed.

## Privacy-preserving local conversion

Only on a machine storing the user's authorized original archive,
run the code-only tool:

```sh
mkdir -p /private/wolfmame-0106/roms
python3 tools/wolfmame0106_private_rom_alias.py \
  --source "/private/original/Cadillac Dinosaur.zip" \
  --out "/private/wolfmame-0106/roms/dino.zip"
```

**All paths above are placeholders**; the private files must actually
be present. The script strictly checks every required game's uncompressed
file length, CRC32 and SHA-1 before creating the output. It refuses unsafe
ZIP entry paths, duplicates, symlinks, oversized contents and overwrites,
then creates a new `dino.zip` with the historical 16 names, preserving
**every decompressed source ROM byte unchanged**. It verifies the finished
ZIP again. The original archive is never modified.

Both input and output must remain **outside the public repository**. The
output archive is created with mode 0600. **Never upload `dino.zip` or
other copyrighted game bytes to GitHub, PRs or public CI artifacts.**
The public PR includes only converter source, historical non-payload
hash metadata, synthetic fixture tests and this documentation.

The newly formed archive can be used as the ROM directory input to the
private Stage279 binary gate and Stage281 replay attempt. For 0.106,
use the correct `dino.zip` name inside the private rompath, but treat
successful `-verifyroms` as prerequisite rather than replay proof.

## Testing

```sh
python3 -m unittest discover -s tests \
  -p 'test_wolfmame0106_private_rom_alias.py' -v
```

Synthetic-only tests use mock content and small artificial ZIPs rather
than real game bytes. The real archive cross-check described above was
performed **outside GitHub** using the user-held Drive ZIP, and no raw
file was pushed to the public repository.

### Remaining limitation

We still need a genuinely compatible WolfMAME 0.106 binary and validated
input playback with observable game frame IDs. MAME 0.106 source ROM
compatibility is strong evidence for game *asset layout*, but it cannot
prove emulator binary authenticity, native gameplay parity, frame
synchronization, or execution on physical Switch.

Stage282 is stacked on Draft PR #89; `main` and approved artwork remain
untouched.

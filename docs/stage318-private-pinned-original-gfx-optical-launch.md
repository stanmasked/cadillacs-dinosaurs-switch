# Stage318 — immutable NRO and NeXium pins before PRIVATE CPS-1 optical playback

Stage317 privately confirmed 14 synthetic-state scenes constructed from the
user's source-authenticated *original static* CPS-1 graphics: all 1,204,224
RGBA pixels agreed between the actual portable Switch C compositor and an
independent Python reference, with zero mismatches.

The remaining Stage316 gate is an **actual local NeXium X11 guest run** on
the user's private original gfx plus synthetic scene state. Merely having
matching C/Python references is not evidence of real host framebuffer
display or original arcade gameplay.

## Why an additional gate?

Stage316 previously accepted any user-supplied NRO and any host emulator
executable as long as the caller gave readable paths. Before passing
user-owned copyrighted game assets to any such process, Stage318 requires
immutable pinned binaries:

| Code-only input | Exact size | SHA-256 |
|---|---:|---|
| Stage316 opt-in ARM64 diagnostic NRO | 313,541 bytes | `8ff351fe9c5bf31d31ab2510908bcdb45bb965c4ea375c024d8b77395a67d0ac` |
| Linux NeXium nightly asset as verified in Stage313 | 114,560,520 bytes | `d96cdd186447eec7a5c05a28fa5aa1b8bb6c8fb85fd7bf76721b349cf2c97dde` |

The first SHA refers to the code-only NRO built on Stage316's final
approved diagnostic commit. It is not a commercial game, ROM dump, firmware
or Nintendo key. **Different opt-in NRO builds must receive their own
explicit source-grounded pin update and revalidation.**

The second refers to the specific binary archive already pinned and used
successfully by NeXium's public ROM-free Stage313/314 runs. The nightly
download URL alone is not an immutable source of trust. Do not trust an
unverified downloaded binary based only on its filename.

## Local private command

Obtain the code-only Stage316 NRO and the independently downloaded
pinned NeXium archive on a private Linux machine. The already-authorized
original MAME 0.106 `dino.zip` must remain OUTSIDE this public repository
and all GitHub/CI storage.

```sh
python3 tools/nexium_private_pinned_optical_launch_318.py \
  --rom /private/roms/dino.zip \
  --nro /private/diagnostics/stage316-optical.nro \
  --nexium-archive /private/diagnostics/pinned-ne-xium.tar.gz \
  --receipt /private/evidence/NEW-stage318-guest-optical-report.json
```

The wrapper checks sizes, full SHA-256 digests, ordinary file types and
absence of symlinked input ancestors before extraction or execution.
The archive is additionally checked for unsafe names, special file
types, excessive members and expansion size. Python 3.12+ data-filtered
extraction is required. The binary is started only through the existing
Stage316 private SD setup and X11 verifier, with a bounded timeout.

The private Stage316 runner independently source-verifies all 16 original
MAME ROM entries, stages original graphics and synthetic scene memory
under temporary isolated HOME/XDG/NeXium SD paths, and compares each
guest-rendered RGBA FNV trace and real X11 optical window capture with
an independent reference before advancing.

## Privacy and evidence meaning

Public Stage318 tests create only toy archives, text pretending to be
NROs and mock subprocess results. No original game's 16 ROM payloads,
derived tile graphics, screenshots, video, guest CSV, original hashes,
input recordings or other game assets are uploaded to public GitHub
branches, CI artifacts or releases.

A future real private Stage318 success would mean only: **14
host-visible synthetic scene states rendered from authentic STATIC original
graphics**. It would not prove original game program execution, original
VRAM/palette/register captures, authentic original gameplay frames,
historical INP/WLF recording replay, audio fidelity, physical Switch
display, or distribution rights. The current public CI cannot perform
the original-data guest run, so its own green status is never reported
as a private optical proof.

This PR remains Draft stacked after Stage317; do not merge into `main`
without explicit authorization.

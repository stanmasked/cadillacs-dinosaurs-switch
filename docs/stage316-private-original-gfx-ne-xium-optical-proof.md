# Stage316 — original CPS-1 graphics + **synthetic** scenes, private NeXium X11 proof

Stage314 conclusively checked all fourteen ROM-free diagnostic CPS-1
frames in two real isolated NeXium cold boots. Stage315 privately
verified all sixteen original `dino.zip` MAME 0.106 members and staged
4,194,304 bytes of user-owned original graphics alongside fourteen
**invented** scene states. None of this establishes original game
execution or original game palette/VRAM/frame capture.

Stage316 creates a ROM-free, code-only **opt-in** ARM64 NRO variant,
compiled with both:

```sh
make -j2 DEFINES="-DDINO_SYNTHETIC_SCENE_GUEST_PROBE -DDINO_PRIVATE_ORIGINAL_GFX_HOST_VISIBLE_316"
```

The Stage316 flag does NOT enable on Stage308 public artificial graphics
signature and is forbidden without guest trace support or together with
the Stage313 synthetic-only optical mode. The **ordinary release NRO
is unchanged**. The opt-in guest writes the same small 14-row diagnostic
CSV after framebuffer submission and draws two magenta calibration
markers and four optical frame-ID bits into the displayed margin.

**The NRO does not authenticate original ROM identity by itself.** Only
the private host gate checks full historical MAME 0.106 source CRC32/SHA1
against all 16 ROM payloads, reconstructs exact 4MiB original graphics
and compares the local `gfx.bin` byte for byte. The 14 scene records
must separately equal the exact artificial Stage307 file. Runtime
state, sprites, palette and layer priorities are SYNTHETIC.

## Local/private run only

Prerequisites: source checkout, your private canonical `dino.zip`,
stage316 opt-in code-only NRO (from devkitPro or CI artifact), pinned
NeXium Linux GUI, Python 3, Pillow, Xvfb, ImageMagick `import`,
xdotool, Mesa software Vulkan. No user keys or original ROM are
ever provided to GitHub Actions.

Use the official SHA256-pinned NeXium release archive from Stage313:
114,560,520 bytes; SHA-256
`d96cdd186447eec7a5c05a28fa5aa1b8bb6c8fb85fd7bf76721b349cf2c97dde`.
Refuse the mutable nightly URL if its downloaded bytes change; verify
the exact NRO build is the Stage316 variant, not an ordinary release.

```sh
bash tools/run_private_original_gfx_optical_316.sh \
    /private/roms/dino.zip \
    /private/stage316-code-only/cadillacs-dinosaurs-switch.nro \
    /private/pinned-nexium/nexium-gui \
    /private/evidence/NEW-stage316-summary.json
```

The script privately rebuilds Stage315 source-authenticated original
graphics in an **isolated temporary directory**, then creates another
isolated NeXium SD/HOME/XDG environment. No previously saved guest
trace/acknowledgment is accepted. Stage316 performs for each of the 14
frames in strict order:

1. Real ARM64 guest NRO writes an ordered `FRAME_SUBMITTED` record
   **after framebufferEnd()**. The native FNV64 scene checksum must
   agree with a newly rendered independent Python reference using the
   private source-authenticated 4MiB graphics.
2. Real host X11 window capture must reveal two calibration beacons,
   the correct optical frame ID, and at least 10 of 25 separately
   sampled reference scene pixels with multiple distinct colors.
3. Only after optical verification, a new exclusive per-frame SD
   `NEXT,i` acknowledgment is written. The guest steps once.
4. The full fourteen-row native trace must have distinct ordered
   frames, matching original-GFX synthetic-scene checksums, and at
   least four distinct sampled framebuffer values.

A negative or missing result returns
`BLOCKED_PRIVATE_ORIGINAL_GFX_NE_XIUM_X11_PROOF`.
Private host screenshots, raw CSV, original SHA/pixel data, private
paths and full emulator console logs are **never included in the report**.
The only retained report uses strict 0600 permissions and aggregate
counters and explicit false flags for real original gameplay,
original VRAM/palette, INP/WLF replay and physical Switch display.
The source ROM and transformed `gfx.bin` stay in private temporary
directories, not in CI, PR attachments, releases, chat artifacts or
GitHub branches.

## Public CI

`.github/workflows/cps1-private-optical-gfx-316.yml` builds an actual
Switch NRO with the Stage316 opt-in C path and tests the verifier with
**invented bytes**. It uploads ONLY the code-only diagnostic NRO for
the user's local private machine. This is not an original-ROM emulator
run and its green status cannot be promoted to authentic game playback.

## Confirmed private optical result — 2026-10-22

A fresh private Stage316 run passed with the pinned NeXium executable under
the Stage323 isolated glibc 2.43 runtime and Mesa Lavapipe. It verified
14/14 native guest submissions and 14/14 process-bound X11 optical frames
against independent references derived from static original graphics plus
invented palette/VRAM/OBJ/priority states. The private receipt remains mode
0600 and is not uploaded.

## Explicit limits

This successful Stage316 run proves only the existing native compositor and
X11 display against real STATIC original graphics plus invented scene states.
It does **not** prove that MAME 0.106 actually ran the original game, an
authentic captured arcade gameplay frame, true recorded controller replay,
sprites in their real positions, original soundtrack, or gameplay fidelity
on physical Nintendo Switch. The real `dino.inp`/`dino.wlf` replay remains
unverified in this environment.

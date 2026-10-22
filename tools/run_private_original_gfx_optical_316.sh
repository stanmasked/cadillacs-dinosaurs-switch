#!/usr/bin/env bash
# Stage316 PRIVATE local-only NeXium optical probe for original CPS-1 gfx.
# ROM and derived gfx are NEVER copied into public GitHub CI or artifacts.
# Usage: bash tools/run_private_original_gfx_optical_316.sh \
#   /private/roms/dino.zip /private/code-only-stage316.nro \
#   /private/pinned/ne-xium-gui /private/evidence/new-stage316.json
set -euo pipefail
if [ "$#" -ne 4 ]; then
  echo "BLOCKED_PRIVATE_STAGE316_MISSING_INPUTS" >&2
  exit 2
fi
# Keep the original path spelling: the Stage315/316 checks must see
# and reject symlinked input archives rather than a pre-resolved alias.
rom="$1"
nro="$(realpath "$2")"
exe="$(realpath "$3")"
receipt="$4"
test -f "$rom" && test -f "$nro" && test -f "$exe"
# Never print private paths, original hashes, original pixels or console logs.
test ! -e "$receipt"
tmp="$(mktemp -d -t private-gfx-stage316-XXXXXXXX)"
chmod 700 "$tmp"
trap 'rm -rf -- "$tmp"' EXIT

# Mandatory Stage315 source CRC32/SHA1 check BEFORE assembling local GFX.
python3 tools/cps1_private_original_gfx_synthetic_sd_315.py \
  --rom "$rom" --out-dir "$tmp/private-stage315-sd" >/dev/null
mkdir -m 700 -p "$tmp/nexium-data/sdmc"
cp -a "$tmp/private-stage315-sd/switch" "$tmp/nexium-data/sdmc/switch"
test "$(stat -c %s "$tmp/nexium-data/sdmc/switch/cadillacs-dinosaurs-switch/gfx.bin")" = 4194304
test "$(stat -c %s "$tmp/nexium-data/sdmc/switch/cadillacs-dinosaurs-switch/sequence.bin")" = 875160
export NEXIUM_DATA_ROOT="$tmp/nexium-data"
export HOME="$tmp/isolated-home"
export XDG_CONFIG_HOME="$tmp/isolated-xdg/config"
export XDG_CACHE_HOME="$tmp/isolated-xdg/cache"
export XDG_DATA_HOME="$tmp/isolated-xdg/data"
mkdir -m 700 -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
export LIBGL_ALWAYS_SOFTWARE=1
driver="$(find /usr/share/vulkan/icd.d -maxdepth 1 -type f -name '*lvp*json' -print -quit 2>/dev/null || true)"
if [ -n "$driver" ]; then export VK_ICD_FILENAMES="$driver"; else unset VK_ICD_FILENAMES; fi
export WGPU_BACKEND=vulkan
export GDK_BACKEND=x11
export NEXIUM_VIDEO_FFMPEG=0

# Do not weaken verification if GUI, X11, guest writes or Python disagree.
xvfb-run -a -s "-screen 0 1280x720x24" \
  timeout --signal=TERM --kill-after=5s 190s \
  python3 tools/nexium_private_original_gfx_optical_316.py \
    --rom "$rom" --exe "$exe" --nro "$nro" \
    --sd-root "$NEXIUM_DATA_ROOT/sdmc" --summary "$receipt"

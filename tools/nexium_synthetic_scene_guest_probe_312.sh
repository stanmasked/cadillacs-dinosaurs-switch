#!/usr/bin/env bash
# Stage312: actual NeXium guest NRO + fully artificial Stage307/308 SD files.
# No game ROM, copyrighted graphics, keys or firmware. Fail closed unless
# all 14 real guest-submitted RGBA hashes match independent Python reference.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "Usage: bash tools/nexium_synthetic_scene_guest_probe_312.sh <NRO> <summary-directory>" >&2
    exit 2
fi
nro="$(realpath "$1")"
out="$(realpath -m "$2")"
mkdir -p "$out"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Generate both files ONLY in newly created temporary off-repository paths.
python3 tools/cps1_rom_free_sd_bundle_310.py --out-dir "$tmp/new-fixture"
mkdir -p "$tmp/nexium-data/sdmc"
cp -a "$tmp/new-fixture/switch" "$tmp/nexium-data/sdmc/switch"
test "$(stat -c %s "$tmp/nexium-data/sdmc/switch/cadillacs-dinosaurs-switch/gfx.bin")" = 4194304
test "$(stat -c %s "$tmp/nexium-data/sdmc/switch/cadillacs-dinosaurs-switch/sequence.bin")" = 875160

# The same independently pinned NeXium nightly already used by the project's
# proven guest-ARM64 training-room workflow. Reject replacement bytes.
release="https://github.com/nexium-emu/nexium-nightly/releases/download/nightly/nexium-linux-x86_64.tar.gz"
expected_sha="c933fbbcf8d1b011de8d4a79c9d8eb55c0678a305947af9388ddb40ce5960a66"
expected_bytes=114182978
curl --fail --location --retry 2 --connect-timeout 20 --max-time 240 \
    "$release" -o "$tmp/nexium.tar.gz" > "$tmp/download.log" 2>&1
test "$(wc -c < "$tmp/nexium.tar.gz" | tr -d '[:space:]')" = "$expected_bytes"
echo "$expected_sha  $tmp/nexium.tar.gz" | sha256sum -c - >/dev/null
tar -tzf "$tmp/nexium.tar.gz" > "$tmp/archive-list.txt"
if grep -Eq '(^/|(^|/)\.\.(\/|$))' "$tmp/archive-list.txt"; then
    echo "BLOCKED_UNSAFE_EMULATOR_ARCHIVE" >&2
    exit 2
fi
mkdir "$tmp/emulator"
tar -xzf "$tmp/nexium.tar.gz" -C "$tmp/emulator" --no-same-owner
exe="$(find "$tmp/emulator" -type f \( -name 'nexium-gui' -o -name 'nexium' \) -print -quit)"
test -n "$exe"
chmod +x "$exe"

# Correct upstream mapping: NeXium uses NEXIUM_DATA_ROOT/sdmc for sdmc:/.
# XDG/HOME and the full fake SD tree are isolated from private user data.
export NEXIUM_DATA_ROOT="$tmp/nexium-data"
export HOME="$tmp/isolated-home"
export XDG_CONFIG_HOME="$tmp/isolated-xdg/config"
export XDG_CACHE_HOME="$tmp/isolated-xdg/cache"
export XDG_DATA_HOME="$tmp/isolated-xdg/data"
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
export LIBGL_ALWAYS_SOFTWARE=1
driver="$(find /usr/share/vulkan/icd.d -maxdepth 1 -type f -name '*lvp*json' -print -quit 2>/dev/null || true)"
if [ -n "$driver" ]; then export VK_ICD_FILENAMES="$driver"; else unset VK_ICD_FILENAMES; fi
export WGPU_BACKEND=vulkan
export GDK_BACKEND=x11
export NEXIUM_VIDEO_FFMPEG=0

# A timeout or a GUI opening is NOT success. The report must have been
# written by actual opt-in native guest code, after framebufferEnd().
set +e
xvfb-run -a -s "-screen 0 1280x720x24" \
    timeout --signal=TERM --kill-after=5s 90s "$exe" "$nro" \
    > "$tmp/private-emulator-log.txt" 2>&1
runtime_rc=$?
set -e
echo "neXium_runtime_exit_code=$runtime_rc"
# A missing/incomplete guest report is always refused. Do not upload full
# emulator logs, raw framebuffer, private path, or screenshot artifacts.
python3 tools/verify_nexium_synthetic_scene_guest_312.py \
    --guest-trace "$NEXIUM_DATA_ROOT/sdmc/cadillacs-synthetic-scene-guest.csv" \
    --summary "$out/stage312-guest-synthetic-scene-summary.json"

#!/usr/bin/env bash
# Attempt REAL Nintendo Switch NRO execution in the NeXium guest.
# Unlike host-C smoke, this must find a guest-written replay report.
# Keys, Nintendo firmware, private ROMs, and commercial assets are not used.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "Usage: bash tools/nexium_guest_replay_probe.sh ci-app.nro evidence-dir" >&2
    exit 2
fi
nro="$(realpath "$1")"
out="$(realpath -m "$2")"
mkdir -p "$out"
scratch="$(mktemp -d)"
pulse_started=0
recorder_pid=""
cleanup() {
    if [ -n "$recorder_pid" ]; then
        kill "$recorder_pid" 2>/dev/null || true
        wait "$recorder_pid" 2>/dev/null || true
    fi
    if [ "$pulse_started" -eq 1 ]; then
        pulseaudio --kill >/dev/null 2>&1 || true
    fi
    # PulseAudio may still be tearing down its private runtime files.
    # Concurrent socket cleanup must not override the verified guest
    # replay and host-monitor results with a spurious CI failure.
    for attempt in 1 2 3; do
        if rm -rf "$scratch" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "WARNING: private emulator scratch cleanup incomplete" >&2
    return 0
}
trap cleanup EXIT
release="https://github.com/nexium-emu/nexium-nightly/releases/download/nightly/nexium-linux-x86_64.tar.gz"
# Release asset digest verified against the public GitHub API on 2026-10-18.
# Mutable tag: reject changed binary, never silently trust a replacement.
expected="0ec2da5d58b6b362a9f0a4c927af0e55d36a0b50d1ab3f035dd075ea12d76761"
{
    echo "scope=REAL_NE_XIUM_GUEST_CI_NO_NINTENDO_ROM"
    echo "emulator=NeXium pinned experimental nightly"
    echo "expected_emulator_sha256=$expected"
    echo "nro_sha256=$(sha256sum "$nro" | cut -d ' ' -f1)"
    echo "host_arch=$(uname -m)"
} > "$out/metadata.txt"
if ! curl -fL --retry 2 --connect-timeout 20 --max-time 240 \
        "$release" -o "$scratch/nexium.tar.gz" \
        > "$out/download.txt" 2>&1; then
    echo "INCONCLUSIVE: emulator download failed" > "$out/result.txt"
    exit 1
fi
if ! echo "$expected  $scratch/nexium.tar.gz" | sha256sum -c - \
        > "$out/emulator-hash-check.txt" 2>&1; then
    echo "BLOCKED: unrecognized emulator release hash" > "$out/result.txt"
    exit 1
fi
tar -tzf "$scratch/nexium.tar.gz" > "$out/archive-files.txt"
# Pinned binary only; refuse potentially dangerous archive entry paths.
if grep -Eq '(^/|(^|/)\.\.(\/|$))' "$out/archive-files.txt"; then
    echo "BLOCKED: unsafe emulator archive paths" > "$out/result.txt"
    exit 1
fi
mkdir -p "$scratch/app"
tar -xzf "$scratch/nexium.tar.gz" -C "$scratch/app" --no-same-owner
exe="$(find "$scratch/app" -type f \( -name 'nexium-gui' -o -name 'nexium' \) -print -quit)"
if [ -z "$exe" ]; then
    echo "INCONCLUSIVE: verified archive has no emulator executable" > "$out/result.txt"
    exit 1
fi
chmod +x "$exe"
export LIBGL_ALWAYS_SOFTWARE=1
driver="$(find /usr/share/vulkan/icd.d -maxdepth 1 -type f -name '*lvp*json' -print -quit 2>/dev/null || true)"
if [ -n "$driver" ]; then export VK_ICD_FILENAMES="$driver"; else unset VK_ICD_FILENAMES; fi
export WGPU_BACKEND=vulkan
export GDK_BACKEND=x11
export NEXIUM_VIDEO_FFMPEG=0
export HOME="$out/isolated-home"
export XDG_CONFIG_HOME="$out/xdg-config"
export XDG_CACHE_HOME="$out/xdg-cache"
export XDG_DATA_HOME="$out/xdg-data"
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
vulkaninfo --summary > "$out/vulkan.txt" 2>&1 || true

# Optional and isolated host-audio observation. No physical audio device,
# original game sound data, firmware or console keys are involved. A private
# PulseAudio null sink gives NeXium an output target and exposes its MONITOR
# PCM. This is distinct from guest audout buffer accounting and from actual
# audible speaker playback.
export XDG_RUNTIME_DIR="$scratch/xdg-runtime"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
echo "host_audio_monitor=unavailable" >> "$out/metadata.txt"
if command -v pulseaudio >/dev/null 2>&1 && \
        command -v pactl >/dev/null 2>&1 && \
        command -v parec >/dev/null 2>&1; then
    if pulseaudio --start --exit-idle-time=-1 \
            > "$out/pulse-startup.txt" 2>&1; then
        pulse_started=1
        if pactl load-module module-null-sink \
                sink_name=dino_ci_sink rate=48000 channels=2 \
                > /dev/null 2>&1 && \
                pactl set-default-sink dino_ci_sink >/dev/null 2>&1; then
            export PULSE_SINK=dino_ci_sink
            # Route ALSA "default" through the same private Pulse server.
            # NeXium's other supported audio APIs can also use PULSE_SINK.
            cat > "$scratch/alsa-pulse.conf" <<'ALSA'
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
ALSA
            export ALSA_CONFIG_PATH="$scratch/alsa-pulse.conf"
            parec --raw --format=s16le --rate=48000 --channels=2 \
                  --device=dino_ci_sink.monitor \
                  > "$out/host-monitor.raw" \
                  2> "$out/pulse-recorder.txt" &
            recorder_pid=$!
            # The recorder must already be alive before starting the NRO.
            sleep 1
            if kill -0 "$recorder_pid" 2>/dev/null; then
                echo "host_audio_monitor=private_pulse_sink_started" \
                    >> "$out/metadata.txt"
            else
                recorder_pid=""
            fi
        fi
    fi
fi

# No false success on launch, 110s timeout, Vulkan initialization or
# simply seeing the emulator GUI. The guest NRO must itself produce the
# bounded 180-tick trace with BOTH independently verified golden hashes.
set +e
xvfb-run -a -s "-screen 0 1280x720x24" \
    bash -c '
      timeout --signal=TERM --kill-after=5s 110s "$1" "$2" > "$3" 2>&1 &
      emulator_pid=$!
      (
        # After 180 ticks should have completed, even under modest
        # software Vulkan performance; guest trace is checked separately.
        sleep 25
        window="$(xdotool search --onlyvisible --name "NeXium" | tail -n1)"
        if [ -n "$window" ]; then
          xdotool windowfocus "$window" || true
          import -window "$window" "$4" 2>/dev/null || true
          # Wait until the NRO's independent 180-tick replay has
          # completed, THEN send normal host X11 keyboard events.
          # Defaults from NeXium controller_config.rs: Z=Y reset,
          # Right=DPad Right, C=A attack, X=B jump, V=X spar.
          # If the emulator does not actually deliver these through
          # HID, the guest witness will stay INCONCLUSIVE.
          sleep 10
          xdotool windowactivate --sync "$window" || true
          xdotool windowfocus "$window" || true
          xdotool keydown z; sleep 0.25; xdotool keyup z
          sleep 1
          xdotool keydown Right; sleep 0.75; xdotool keyup Right
          sleep 0.3
          xdotool keydown c; sleep 0.25; xdotool keyup c
          sleep 0.3
          xdotool keydown x; sleep 0.25; xdotool keyup x
          sleep 0.3
          xdotool keydown v; sleep 0.25; xdotool keyup v
        fi
      ) >/dev/null 2>&1 &
      wait "$emulator_pid"
    ' bash "$exe" "$nro" "$out/emulator-stdout.txt" "$out/guest-window.png"
rc=$?
set -e
echo "emulator_exit_code=$rc" >> "$out/metadata.txt"
if [ -n "$recorder_pid" ]; then
    kill "$recorder_pid" 2>/dev/null || true
    wait "$recorder_pid" 2>/dev/null || true
    recorder_pid=""
fi
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-arena-selftest.csv' -print \
    > "$out/guest-trace-locations.txt"
if [ -s "$out/guest-trace-locations.txt" ]; then
    IFS= read -r path < "$out/guest-trace-locations.txt"
    cp "$path" "$out/guest-replay.csv"
fi
python3 tools/verify_nexium_guest_replay.py \
    --report "$out/guest-replay.csv" \
    --out "$out/result.txt"

# No host-sink audio classification is published unless the guest's
# independently verified replay and native audio adapter counters passed.
python3 tools/verify_nexium_host_audio.py \
    --raw "$out/host-monitor.raw" \
    --out "$out/host-audio-evidence.json"

# The optional HID result is validated only from a separate file that
# must be created by the running NRO *after* its 180-tick replay.
# Host attempts to send keys cannot themselves establish controller success.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-controller-selftest.csv' -print \
    > "$out/guest-controller-locations.txt"
if [ -s "$out/guest-controller-locations.txt" ]; then
    IFS= read -r controller_path < "$out/guest-controller-locations.txt"
    cp "$controller_path" "$out/guest-controller.csv"
fi
python3 tools/verify_nexium_guest_controller.py \
    --report "$out/guest-controller.csv" \
    --out "$out/guest-controller-evidence.json"

# A guest-written CSV alone proves native execution, but not pixels.
# Check that the actual 1280x720 NeXium window contains expected
# ROM-free arena colors in background, two actors and bottom HUD.
# The coordinates are away from the emulator performance overlay.
if [ ! -s "$out/guest-window.png" ]; then
    echo "INCONCLUSIVE: guest trace passed but no emulator window pixels captured" > "$out/result.txt"
    exit 1
fi
dimensions="$(identify -format '%wx%h' "$out/guest-window.png" 2>/dev/null || true)"
colors="$(convert "$out/guest-window.png" -format \
    '%[pixel:p{100,200}]|%[pixel:p{100,300}]|%[pixel:p{748,430}]|%[pixel:p{800,400}]|%[pixel:p{100,640}]' \
    info: 2>/dev/null || true)"
expected_colors='srgb(30,61,70)|srgb(62,83,74)|srgb(62,180,208)|srgb(190,126,74)|srgb(11,18,29)'
if [ "$dimensions" != "1280x720" ] || [ "$colors" != "$expected_colors" ]; then
    echo "INCONCLUSIVE: emulator window framebuffer colors mismatch known ROM-free geometry" > "$out/result.txt"
    exit 1
fi
echo "PASS: actual NeXium NRO guest 180-tick replay, two hashes and visible framebuffer pixels verified; audible device sound unverified" > "$out/result.txt"
echo "PASS: original ROM-free emulator window pixel markers confirmed" > "$out/frame-pixels.txt"

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
# Stage 247 CI recovered from a nightly asset replacement on 2026-10-20:
# verified via GitHub's public official release-asset API metadata.
# Release asset id=658656899 (nexium-linux-x86_64.tar.gz), 114182978 bytes;
# API asset digest sha256:c933fbbcf8d1b011de8d4a79c9d8eb55c0678a305947af9388ddb40ce5960a66
# Mutable nightly tag: ALWAYS reject any future unexpected asset bytes.
# This is a new emulator revision, not a claim of gameplay compatibility.
expected="c933fbbcf8d1b011de8d4a79c9d8eb55c0678a305947af9388ddb40ce5960a66"
expected_size=114182978
{
    echo "scope=REAL_NE_XIUM_GUEST_CI_NO_NINTENDO_ROM"
    echo "emulator=NeXium pinned experimental nightly"
    echo "expected_emulator_sha256=$expected"
    echo "expected_emulator_bytes=$expected_size"
    echo "expected_release_asset_id=658656899"
    echo "nro_sha256=$(sha256sum "$nro" | cut -d ' ' -f1)"
    echo "host_arch=$(uname -m)"
} > "$out/metadata.txt"
if ! curl -fL --retry 2 --connect-timeout 20 --max-time 240 \
        "$release" -o "$scratch/nexium.tar.gz" \
        > "$out/download.txt" 2>&1; then
    echo "INCONCLUSIVE: emulator download failed" > "$out/result.txt"
    exit 1
fi
if [ "$(wc -c < "$scratch/nexium.tar.gz" | tr -d '[:space:]')" != "$expected_size" ]; then
    echo "BLOCKED: emulator release asset size mismatch" > "$out/result.txt"
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
      timeout --signal=TERM --kill-after=5s 155s "$1" "$2" > "$3" 2>&1 &
      emulator_pid=$!
      (
        # After 180 ticks should have completed, even under modest
        # software Vulkan performance; guest trace is checked separately.
        sleep 25
        window="$(xdotool search --onlyvisible --name "NeXium" | tail -n1)"
        if [ -n "$window" ]; then
          xdotool windowfocus "$window" || true
          import -window "$window" "$4" 2>/dev/null || true
          # After the 180-tick guest replay, use a single host
          # monotonic clock to time sampled X11 pixel response to
          # the keyboard Right event. The new probe also delivers
          # Y reset + A/B/X actions and records only a bounded JSON
          # summary, never screenshots or raw keyboard events.
          sleep 10
          python3 tools/nexium_host_input_pixel.py \
              --window "$window" --out "$5" \
              --audio-out "$6" || true
          # The JSON is deliberately sanitized: summary/status only,
          # no captured image, window title or host-clock timestamp.
          if [ -f "$5" ]; then cat "$5" >&2; fi
          # A missing pixel sampler must never prevent the existing
          # guest-HID test from receiving all five original actions.
          # Only the guest-written timeline can prove HID delivery.
          if ! grep -q HOST_PIXEL_CHANGE_OBSERVED_UNBOUND "$5" 2>/dev/null &&
             python3 tools/nexium_hid_fallback_guard.py \
               "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"; then
            # A missing host pixel is not a reason to reset a guest whose
            # actual HID witness is complete or whose stress CSV exists.
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
          # Optional Stage 234 external T/ZR after guest stress finishes.
          # A host key attempt alone never establishes in-guest delivery.
          python3 tools/nexium_counter_hid_press.py \
            --window "$window" \
            --root "$HOME" --root "$XDG_CONFIG_HOME" \
            --root "$XDG_CACHE_HOME" --root "$XDG_DATA_HOME" \
            --out "$7" || true
          # Stage 244: the guest runs an unstaged ROM-free enemy chase
          # over 116 native simulation ticks and writes a ready marker.
          # This second *host attempt* is never accepted as game evidence.
          python3 tools/nexium_natural_counter_hid_press.py \
            --window "$window" \
            --root "$HOME" --root "$XDG_CONFIG_HOME" \
            --root "$XDG_CACHE_HOME" --root "$XDG_DATA_HOME" \
            --out "$8" || true
          # Stage 246: another real Y / X / T sequence, gated by
          # previous genuine natural ZR. This time the game-state
          # witness must come from the actual *rendered* arena.
          python3 tools/nexium_live_counter_hid_press.py \
            --window "$window" \
            --root "$HOME" --root "$XDG_CONFIG_HOME" \
            --root "$XDG_CACHE_HOME" --root "$XDG_DATA_HOME" \
            --out "$9" --host-counter-out "${10}" \
            --host-frame-token-out "${11}" \
            --host-capture-window-out "${12}" \
            --host-command-bracket-out "${13}" || true
        fi
      ) >/dev/null 2>&1 &
      wait "$emulator_pid"
    ' bash "$exe" "$nro" "$out/emulator-stdout.txt" "$out/guest-window.png" "$out/host-pixel-raw.json" "$out/host-spar-raw.json" "$out/host-zr-attempt.json" "$out/host-natural-zr-attempt.json" "$out/host-live-zr-attempt.json" "$out/host-counter-window-evidence.json" "$out/host-frame-token-evidence.json" "$out/host-capture-window-evidence.json" "$out/host-keydown-bracket-evidence.json"
rc=$?
set -e
echo "emulator_exit_code=$rc" >> "$out/metadata.txt"
# This report has fixed, path-free fields and no raw image/input data.
# Emit after the Xvfb subshell so CI logs can distinguish a missing
# baseline pixel from an unavailable sampler without artifact download.
if [ -s "$out/host-pixel-raw.json" ]; then
    cat "$out/host-pixel-raw.json"
fi
if [ -s "$out/host-spar-raw.json" ]; then
    cat "$out/host-spar-raw.json"
fi
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

# Stage 229: an independent scripted counter + original synthesized
# PCM proof written by the REAL guest NRO before the 180-tick replay.
# This is NOT an HID ZR press and MUST NOT be reported as one.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-counter-guest.csv' -print \
    > "$out/counter-guest-locations.txt"
if [ -s "$out/counter-guest-locations.txt" ]; then
    IFS= read -r counter_path < "$out/counter-guest-locations.txt"
    cp "$counter_path" "$out/guest-counter.csv"
fi
python3 tools/verify_nexium_guest_counter.py \
    --report "$out/guest-counter.csv" \
    --out "$out/guest-counter-evidence.json"

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

# Independently verify strict RESET -> MOVE -> ATTACK -> JUMP -> SPAR
# effect ordering in *guest* 60Hz ticks. These tick gaps do not represent
# host keyboard latency or audio/speaker delivery.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-hid-timeline.csv' -print \
    > "$out/hid-timeline-locations.txt"
if [ -s "$out/hid-timeline-locations.txt" ]; then
    IFS= read -r timeline_path < "$out/hid-timeline-locations.txt"
    cp "$timeline_path" "$out/guest-hid-timeline.csv"
fi
python3 tools/verify_nexium_hid_timeline.py \
    --report "$out/guest-hid-timeline.csv" \
    --summary "$out/guest-controller.csv" \
    --out "$out/guest-hid-timeline-evidence.json"

# Stage 137: the actual guest must continue for 900 simulation ticks
# AFTER the independently verified native X11->HID game actions.
# This is a separate audout queue health witness; missing/stalled guest
# evidence reports INCONCLUSIVE without changing the baseline NRO PASS.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-audio-stress.csv' -print \
    > "$out/audio-stress-locations.txt"
if [ -s "$out/audio-stress-locations.txt" ]; then
    IFS= read -r stress_path < "$out/audio-stress-locations.txt"
    cp "$stress_path" "$out/guest-audio-stress.csv"
fi
python3 tools/verify_nexium_audio_stress.py \
    --report "$out/guest-audio-stress.csv" \
    --timeline "$out/guest-hid-timeline.csv" \
    --controller "$out/guest-controller.csv" \
    --out "$out/guest-audio-stress-evidence.json"

# Optional real libnx ZR edge. Only the NRO can write this guest CSV.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-counter-hid.csv' -print \
    > "$out/counter-hid-locations.txt"
if [ -s "$out/counter-hid-locations.txt" ]; then
    IFS= read -r counter_hid_path < "$out/counter-hid-locations.txt"
    cp "$counter_hid_path" "$out/guest-counter-hid.csv"
fi
python3 tools/verify_nexium_guest_counter_hid.py \
    --report "$out/guest-counter-hid.csv" \
    --out "$out/guest-counter-hid-evidence.json"

# Optional Stage 244: guest-owned marker + naturally timed second ZR.
# The CSV is created only after full 60-Hz AI pursuit from a normal reset.
# A late or undelivered host press must yield INCONCLUSIVE, not success.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-natural-counter-hid.csv' -print \
    > "$out/natural-counter-locations.txt"
if [ -s "$out/natural-counter-locations.txt" ]; then
    IFS= read -r natural_counter_path < "$out/natural-counter-locations.txt"
    cp "$natural_counter_path" "$out/guest-natural-counter-hid.csv"
fi
python3 tools/verify_nexium_guest_natural_counter_hid.py \
    --report "$out/guest-natural-counter-hid.csv" \
    --out "$out/guest-natural-counter-hid-evidence.json"

# Stage 246 optional: the real *visible scene arena* must have consumed
# Y reset, X spar, its own 116-tick pursuit and a third real T/ZR.
# A host attempt is never enough; absent native guest CSV is INCONCLUSIVE.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-live-counter-hid.csv' -print \
    > "$out/live-counter-locations.txt"
if [ -s "$out/live-counter-locations.txt" ]; then
    IFS= read -r live_counter_path < "$out/live-counter-locations.txt"
    cp "$live_counter_path" "$out/guest-live-counter-hid.csv"
fi
python3 tools/verify_nexium_guest_live_counter_hid.py \
    --report "$out/guest-live-counter-hid.csv" \
    --out "$out/guest-live-counter-hid-evidence.json"

# Stage 248 independent *native guest framebuffer* sampling. This is
# emitted only after the NRO's own arena_frame() and framebufferEnd(),
# not inferred from gameplay state or an X11 window screenshot.
# First pass remains optional; missing pixels explicitly INCONCLUSIVE.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-live-counter-framebuffer.csv' -print \
    > "$out/guest-counter-framebuffer-locations.txt"
if [ -s "$out/guest-counter-framebuffer-locations.txt" ]; then
    IFS= read -r guest_framebuffer_path < "$out/guest-counter-framebuffer-locations.txt"
    cp "$guest_framebuffer_path" "$out/guest-live-counter-framebuffer.csv"
fi
python3 tools/verify_nexium_guest_counter_framebuffer.py \
    --report "$out/guest-live-counter-framebuffer.csv" \
    --live-csv "$out/guest-live-counter-hid.csv" \
    --out "$out/guest-live-counter-framebuffer-evidence.json"
# Stage 253: save diagnostic-only list of actual submitted counter frame IDs.
# The host token and guest frame trace stay separate until verified; a
# missing marker is INCONCLUSIVE rather than fabricated proof.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-live-counter-frame-tokens.csv' -print \
    > "$out/guest-frame-token-locations.txt"
if [ -s "$out/guest-frame-token-locations.txt" ]; then
    IFS= read -r token_path < "$out/guest-frame-token-locations.txt"
    cp "$token_path" "$out/guest-live-counter-frame-tokens.csv"
fi

# Optional frame-level cross-domain evidence. Always fail closed if a
# pixel, native frame token or exact binary witness is absent.
python3 tools/verify_nexium_host_frame_token.py \
    --host-token "$out/host-frame-token-evidence.json" \
    --host-window "$out/host-counter-window-evidence.json" \
    --guest-trace "$out/guest-live-counter-frame-tokens.csv" \
    --guest-framebuffer "$out/guest-live-counter-framebuffer.csv" \
    --metadata "$out/metadata.txt" \
    --nro "$nro" \
    --out "$out/host-guest-frame-token-evidence.json"
# Stage 255: raw host X11 sampling-window JSON is collected here.
# Its independent validation must happen AFTER the workflow has created
# guest-audio-mode-binding.json from the completed native 900-tick report.




# Stage 208: guest-selftest-only per-tick ACK observation log. This is
# when polling *noticed* a page return, never a service or speaker timestamp.
# Require this log and match all 900 ticks against the verified aggregate
# guest stress report. Do not silently substitute synthetic observations.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-audio-ack-ticks.csv' -print \
    > "$out/audio-ack-tick-locations.txt"
if [ -s "$out/audio-ack-tick-locations.txt" ]; then
    IFS= read -r ack_tick_path < "$out/audio-ack-tick-locations.txt"
    cp "$ack_tick_path" "$out/guest-audio-ack-ticks.csv"
fi
python3 tools/verify_nexium_audio_ack_tick_trace.py \
    --trace "$out/guest-audio-ack-ticks.csv" \
    --report "$out/guest-audio-stress-evidence.json" \
    --mode "$DINO_AUDIO_MODE" \
    --out "$out/guest-audio-ack-tick-evidence.json"

# Selftest-only bounded RAM clock witness: this CSV is dumped AFTER the
# 900 game ticks, with the loop's ALREADY capped armTicksToNs interval.
# A fake or incomplete clock trace cannot silently satisfy this gate.
find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    -type f -name 'cadillacs-guest-frame-clock.csv' -print \
    > "$out/guest-frame-clock-locations.txt"
if [ -s "$out/guest-frame-clock-locations.txt" ]; then
    IFS= read -r guest_clock_path < "$out/guest-frame-clock-locations.txt"
    cp "$guest_clock_path" "$out/guest-frame-clock.csv"
fi
python3 - "$out/guest-frame-clock.csv" \
    "$out/guest-audio-ack-ticks.csv" \
    "$out/guest-audio-stress-evidence.json" \
    "$DINO_AUDIO_MODE" \
    "$out/guest-frame-clock-evidence.json" <<'PY'
import json
from pathlib import Path
import sys
from tools import verify_nexium_guest_frame_clock as clock

result=clock.verify_one(*sys.argv[1:5])
with Path(sys.argv[5]).open('x',encoding='ascii') as out:
    out.write(json.dumps(result,sort_keys=True)+'\n')
print(json.dumps({
    'status':result['status'],
    'mode':result['mode'],
    'frame_rows':result['frame_rows'],
    'guest_nro_sha256_attested':False,
},sort_keys=True))
PY



# Explicit opt-in only: re-verify actual guest-ramp state *after* its
# recorded 900 simulation ticks. This must never run for normal baseline
# or extra-poll NRO jobs. No return file => no success, not a fake zero.
if [ "${DINO_GUEST_RESUME_RAMP_REQUIRE:-0}" = 1 ]; then
    if [ "$DINO_AUDIO_MODE" != baseline ]; then
        echo "opt-in ramp evidence requires baseline audio poll mode" >&2
        exit 1
    fi
    find "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
        -type f -name 'cadillacs-guest-resume-ramp.csv' -print \
        > "$out/resume-ramp-locations.txt"
    if [ -s "$out/resume-ramp-locations.txt" ]; then
        IFS= read -r resume_path < "$out/resume-ramp-locations.txt"
        cp "$resume_path" "$out/guest-resume-ramp.csv"
    fi
    python3 tools/verify_nexium_guest_resume_ramp.py \
        --ramp "$out/guest-resume-ramp.csv" \
        --trace "$out/guest-audio-ack-ticks.csv" \
        --report "$out/guest-audio-stress-evidence.json" \
        --nro "$nro" \
        --out "$out/guest-resume-ramp-evidence.json"
fi


# Accept the software-only host-window sample bound ONLY after the
# guest's ordered HID witness is verified. The result is explicitly
# NOT an actual controller, hardware display or audio latency.
python3 tools/verify_nexium_host_input_bound.py \
    --host "$out/host-pixel-raw.json" \
    --timeline "$out/guest-hid-timeline.csv" \
    --controller "$out/guest-controller.csv" \
    --out "$out/host-input-bound-evidence.json"

# A separate Pulse monitor receives the invented 530Hz spar tone.
# Never accept its sampled audio-read response unless the actual NRO
# independently witnessed the real HID spar toggle in sequence.
python3 tools/verify_nexium_spar_audio_bound.py \
    --host "$out/host-spar-raw.json" \
    --timeline "$out/guest-hid-timeline.csv" \
    --controller "$out/guest-controller.csv" \
    --out "$out/host-spar-audio-evidence.json"

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

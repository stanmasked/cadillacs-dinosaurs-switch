# Stage319 — bind the private NeXium X11 optical window to its launch

Stage314 established repeatable host-visible parity for 14 ROM-free
synthetic CPS-1 scenes in two independent NeXium cold boots. Stage317
privately verified 14 C/Python scenes made with **real original static
graphics plus invented scroll/VRAM/palette/OBJ/priority state**.

Stage316 introduced a local-only NeXium optical capture pipeline for
the original graphics, but its host window locator trusted the *window
title* alone. If another NeXium instance was already running, it might
capture the wrong host window. Stage319 makes that failure **fail closed**.

## New binding

The private Stage316 host verifier now uses
`nexium_x11_process_window_319.window_for_process(proc.pid)` instead of
the unscoped Stage313 window-title search:

1. Spawn the actual pinned NeXium executable within the local-only
   Stage316 runner. The process PID is known to the subprocess owner.
2. Enumerate the bounded list of X11 windows whose title matches
   NeXium, then query each candidate's X11-reported `_NET_WM_PID`
   via `xdotool getwindowpid`.
3. Match only an exact process PID or a live descendant process,
   using bounded Linux `/proc/<pid>/status` parent traversal.
4. Refuse absent/invalid WM PIDs, stale windows owned by another
   emulator, ambiguous multiple same-run windows, unsupported process
   trees, cycles, inaccessible `/proc`, or missing `xdotool`.
5. Only if one unique window matches, capture its actual X11 pixels,
   verify both magenta optical calibrators, decode the expected frame
   barcode and match at least 10 reference pixels before sending
   the next private guest SD acknowledgment.

This adds process-scoped provenance, but **X11 `_NET_WM_PID` is a
client-controlled property and is not cryptographic proof against a
malicious X11 client**. A spoofed property, unusual NeXium launcher
process tree or multiple windows can cause refusal rather than a
false success. It does not prove original game execution or Switch
hardware display.

## Private reproduction

Use the immutable code-only Stage316 ARM64 diagnostic NRO and verified
NeXium archive from Stage318, your own source-hash-verified canonical
`dino.zip`, and the **new Stage319 public source-only kit** which
includes the modified Stage316 verifier and new process binding:

```sh
python3 tools/nexium_private_pinned_optical_launch_318.py \
  --rom /private/roms/dino.zip \
  --nro /private/binaries/stage316-optin.nro \
  --nexium-archive /private/binaries/pinned-nexium.tar.gz \
  --receipt /private/evidence/NEW-stage319-optical.json
```

The private launcher still verifies immutable NRO/NeXium pins and
original ROM contents before staging local-only original graphics,
then verifies 14 guest-submitted frames against Python and real
process-owned X11 snapshots. **Do not upload any original game ROM,
derived GFX, X11 screenshots, guest traces or private host log.**
Only a local redacted 0600 aggregate receipt is permitted.

## Public regressions

`.github/workflows/cps1-private-x11-process-binding-319.yml`
runs entirely ROM-free mock-process tests covering same-run and
descendant PID acceptance; unrelated, stale, spoofed, missing and
ambiguous PID rejection; short/long malformed X11 lookup responses;
process ancestry cycles and limits; and Stage316's real call site.
It also compiles the public portable C scene compositor and creates
a code-only archive containing public Python, public C/H sources, and
the Stage316 shell script — no original media, NRO or emulator binary.

The original-graphics NeXium run remains **not yet independently
confirmed**, even if this public CI workflow passes. The current
development container has no installed pinned NeXium GUI, xdotool, or
software Vulkan driver, and direct download of the pinned archive
is unavailable; no X11 result will be claimed until an actual
guest-and-host opt-in run succeeds.

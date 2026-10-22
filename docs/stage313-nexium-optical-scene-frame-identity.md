# Stage313 — bind actual NeXium X11 pixels to all fourteen synthetic guest frames

Stage312 proved the ARM64 guest decoded and submitted 14 ROM-free invented
CPS-1 scenes, with the native 384x224 RGBA matching independent Python.
It did not establish that the *host-visible NeXium window* showed them.

Stage313 is a separate, compile-time **opt-in** NRO variant requiring
`-DDINO_SYNTHETIC_SCENE_GUEST_PROBE -DDINO_SYNTHETIC_SCENE_HOST_VISIBLE_313`.
It never runs in ordinary release NRO and does not affect the normal
arena, controller replay, audio stress or original ROM privacy gate.

## Optical synchronization

Only for the Stage308 artificial gfx marker and exact Stage307 14-scene,
2 FPS CPS1SEQ1 sequence:

1. Pause the guest after it submits scene 0, writing its Stage312
   `FRAME_SUBMITTED,index,scene_fnv64,screen_fnv64` record.
2. The guest draws a four-bit, red/green optical scene index and a magenta
   locator in the left margin of its **actual submitted framebuffer**;
   those visual markers do not alter the CPS-1 scene RGBA.
3. The host obtains an **actual screenshot of the NeXium X11 window** in
   a private temporary directory, locates and decodes the optical index,
   then samples 25 scene positions after calibrating display offset and
   scale using the marker geometry.
4. Host scene pixels must match a separately generated synthetic Python
   reference at ten or more positions with multiple color values. A
   changing GUI alone or a barcode drawn over an empty scene is
   insufficient.
5. Only after the matching host screenshot is observed does the host
   atomically write `NEXT,i` to the isolated NeXium SD. The guest reads
   the acknowledgment and advances one frame. Repeat until all 14
   ordered scene IDs are captured.
6. The verifier rechecks the entire **real guest-written** Stage312
   record against independent Python RGBA. Any missing guest file, out
   of order barcode, empty/stale host pixels, emulator timeout or
   invalid reference refuses success.

NeXium's host SD mapping is `NEXIUM_DATA_ROOT/sdmc/`; the workflow
generates *only* the public deterministic ROM-free Stage307/308 files in
a newly created isolated external staging root, downloads the NeXium
release with a fixed SHA-256 and exact size, then runs the opt-in NRO
inside Xvfb using software Vulkan.

## Reproduction

The mock-only checker and source tests can run locally:

~~~sh
python3 -m pip install Pillow==11.3.0
python3 -m unittest discover -s tests \
  -p 'test_nexium_optical_frame_capture_313.py' -v
~~~

**Those local mocks are not evidence of a real emulator run.** The
real proof is the separately gated
`.github/workflows/cps1-optical-scene-guest-313.yml`, which builds the
actual NRO in devkitPro and captures the real X11 window while the NRO
runs. Screenshots, raw guest CSV, emulator console, original ROM data,
private keys and private filesystem paths are not uploaded. Only the
aggregate `stage313-guest-host-optical-summary.json` is retained.

Success would verify host-visible pixels from all 14 **artificial**
scenes and an optical identity matching the guest. It would **not**
verify original Cadillacs and Dinosaurs gameplay, original MAME frames,
historical INP/WLF playback, a physical Switch screen, audio quality or
precise GPU scanout timing. Keep Draft, stacked on Stage312, and do not
merge into `main` solely because synthetic tests pass.

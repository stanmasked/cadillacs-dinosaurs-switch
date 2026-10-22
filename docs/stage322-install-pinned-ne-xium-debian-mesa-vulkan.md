# Stage322 — actual NeXium and Mesa Vulkan provisioning for private replay

The current user-provided private ROM lives outside GitHub. The local
Debian 13 session has the Vulkan loader and Xvfb but does NOT have a
Mesa Lavapipe software ICD, an installed NeXium executable, apt package
lists, usable DNS, or a network-capable curl invocation. Claiming an
emulator run in that environment would be incorrect.

Stage322 uses GitHub Actions' networking **only for publicly available
emulator binaries and free-software driver packages**. No original
game ROM, derived `gfx.bin`, private screenshots, keys, private
save data, traces or input movie are uploaded.

## Two independent installation results

1. Ubuntu 24.04 GitHub runner installs Mesa Lavapipe using real
   `apt-get`, selects `lvp` Vulkan ICD, runs `vulkaninfo --summary`
   and confirms a real software Vulkan 1.3-capable device. It obtains
   the Linux NeXium public release and REQUIRES its **exact**
   previously recorded immutable SHA256
   `d96cdd186447eec7a5c05a28fa5aa1b8bb6c8fb85fd7bf76721b349cf2c97dde`
   and **114,560,520 bytes**. The mutable nightly link is never
   trusted without this check. Safe Python data-filter extraction
   occurs only after both checks, and the native executable is
   validated with `ldd`. Only the public pinned NeXium release
   archive and bounded status manifest enter a one-day CI artifact.
2. A separate `debian:trixie` container downloads genuine Debian 13
   `.deb` packages for `mesa-vulkan-drivers`, `vulkan-tools`,
   `libvulkan1` and required dependencies. Each package SHA256
   is recorded; only those public system packages enter a one-day
   artifact. This supports **offline installation** into a matching
   private Debian 13 environment whose DNS is restricted.

Both are free/open-source public host runtime provisioning. They
are NOT private original ROM guest execution.

## Offline local environment (Debian 13)

After CI succeeds, inspect and extract only the signed/digest-verified
public Debian package artifacts into a private host workspace outside
the ROM repository. Apply package-manager installation locally with
`dpkg -i` when dependencies are satisfied (prefer a disposable Debian
13 environment, NOT forced host package replacement). The release tar
must be rechecked locally with SHA256 and size before extraction.
The Vulkan loader should point at Mesa's Lavapipe ICD `lvp_icd.*json`;
confirm real Vulkan `vulkaninfo --summary` before launching NeXium.

Finally use the already tested local-only Stage318 NeXium runner with
the source-verified private original `dino.zip`, the opt-in Stage316
NRO, and process-bound Xlib capture from Stage321. A true private
NeXium result requires the 14 post-submission guest rows AND the
corresponding 14 X11 host-window optical frames. Successful provisioning
by itself is NOT a guest or gameplay parity proof.

## Safe failure rules

If apt mirrors cannot be reached, if a pinned archive changed,
if Mesa's ICD is unavailable, if `vulkaninfo` fails, if NeXium has
missing shared libraries or an unsafe tar member, or if CI upload
fails, mark the specific stage BLOCKED. Never silently fall back to a
different unpinned release, a mock Vulkan device, a substituted window
or a public ROM upload.

No Nintendo Switch firmware, keys or original game resources are
necessary for the public download/install checks.

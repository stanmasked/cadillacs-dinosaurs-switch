# Cadillacs and Dinosaurs — Nintendo Switch HD Remake

Target: **Capcom CPS-1, World 930201, MAME dino**.

## Current status
Initial Switch homebrew bootstrap and ROM auditing framework. **Not yet playable.** No original commercial assets are stored here.

## Build
Install [devkitPro switch-dev](https://www.switchbrew.org/wiki/Setting_up_Development_Environment), export DEVKITPRO, then run `make`. Expected result: `cadillacs-dinosaurs-switch.nro`. Switch compilation is not yet verified.

## ROM audit
Run `python3 tools/verify_rom.py /path/to/your/dino.zip` using your own legitimately acquired files. Never commit ROM data.

## Milestones
1. Audit original CPS-1 ROMs and establish gameplay references.
2. Create a deterministic gameplay-faithful runtime baseline.
3. Implement Switch video, audio and local controllers.
4. Restore HD sprites, stages, interface and effects.
5. Test co-op, performance, levels and original input timing.

## Intellectual property
Cadillacs and Dinosaurs belongs to its respective owners. Distribution of original assets or a public IP-based remake requires appropriate rights.
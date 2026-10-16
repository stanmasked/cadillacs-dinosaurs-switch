# Experimental dino VBlank sprite-buffer capture in MAME

MAME CPS-1 video_start allocates the 0x800-byte m_buffered_obj. At each
VBlank cps1_objram_latch() copies current m_obj into this buffered memory,
and cps1_render_sprites() reads this latched copy. Capturing current GFX
RAM or an unlatched object table is not equivalent.

## Locally instrument your own MAME checkout

From the Cadillacs and Dinosaurs project, generate a small unified patch:

    python3 tools/mame_obj_instrument.py /your/mame/src/mame/capcom/cps1_v.cpp --patch /tmp/dino-obj-latch.patch

Apply to your privately maintained MAME checkout:

    cd /your/mame
    git apply --check /tmp/dino-obj-latch.patch
    git apply /tmp/dino-obj-latch.patch

Rebuild MAME with its usual tooling. Neither the original MAME source
nor ROM data is included in our GitHub repository.

## Restrict capture to a bounded window

Create the dump directory and set all THREE environment variables:

    mkdir -p /private/cps1-obj
    export CPS1_OBJ_DUMP_DIR=/private/cps1-obj
    export CPS1_OBJ_DUMP_START=900
    export CPS1_OBJ_DUMP_COUNT=6
    /path/to/instrumented/mame dino -rompath /private/mame-roms

Only game ID dino is instrumented. This example writes latch event
frames 900 through 905, not necessarily SCREEN frames 900 through 905.
The count is limited to 1..120; missing variables disable capture.

Each file is named dino_obj_latch_frame-00000900.be.bin (etc.), contains
2048 bytes and stores 1024 big-endian words. Verify files locally:

    python3 tools/mame_obj_validate.py /private/cps1-obj/dino_obj_latch_frame-00000900.be.bin --output /private/cps1-obj/obj-900-report.json

The validator records SHA-256, optional 0xffxx terminator and original
latch frame number.

## Important timing limitation

The VBlank latch and frame_done screen output are distinct phases. CPS-1
sprites are delayed by one frame. A matching filename frame number does
NOT establish which displayed screenshot contains those sprites. All
captures are initially marked framebuffer_synchronized=false and
pixel_parity_eligible=false.

Pixel-exact parity should be claimed only after determining the render
phase and comparing the actual reconstructed reference frames.

## Tests

    python3 -m unittest discover -s tests -p test_mame_obj_capture.py -v

The tests include C++17 compilation and execution of the *instrumented*
CPS-1 latch method using a minimal MAME stand-in. They validate byte
count/order and error conditions. This does not establish that actual
MAME was compiled or run with the game.

Authoritative reference:
https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1_v.cpp

ROMs, captured sprites, screenshots and MAME-generated files must stay
outside GitHub.

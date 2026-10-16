-- dino World 930201: EXPERIMENTAL local-only MAME 0.289 reference capture.
-- Captures original MAME RGB/framebuffer and CPS-1 shared memory.
-- Does NOT capture internal VBlank-latched OBJ; NEVER claim pixel parity.
local OUTPUT_DIR='cps1-captures'
local START_FRAME=900
local FRAME_COUNT=6
local FRAME_STEP=2

local machine=manager.machine
local cpu=assert(machine.devices[':maincpu'],'Missing :maincpu')
local screen=assert(machine.screens[':screen'],'Missing :screen')
local palette=assert(machine.palettes[':palette'],'Missing :palette')
local space=assert(cpu.spaces['program'],'Missing 68000 program space')
local shares=machine.memory.shares
local gfx=assert(shares[':gfxram'],'Missing :gfxram')
local cps_a=assert(shares[':cps_a_regs'],'Missing :cps_a_regs')
local cps_b=assert(shares[':cps_b_regs'],'Missing :cps_b_regs')
assert(gfx.size>=0x30000,'dino QSound gfxram must map 0x30000 bytes')
assert(cps_a.size>=0x40 and cps_b.size>=0x40,'Missing 0x40-byte CPS registers')
assert(palette.entries>=0xc00,'Expected 3072 effective palette colors')

-- Different versions of MAME share:read_u16 may interpret offset as bytes
-- or words. Calibrate against real 68000 address-space reads; never guess.
local function detect_word_step()
    local byte_matches,word_matches=0,0
    for i=0,15 do
        local index=(i*229+17)%0x17fff
        local expected=space:read_u16(0x900000+index*2)
        if gfx:read_u16(index*2)==expected then byte_matches=byte_matches+1 end
        if gfx:read_u16(index)==expected then word_matches=word_matches+1 end
    end
    assert(byte_matches>=14 or word_matches>=14,
           string.format('MAME memory share calibration failed: %d/%d',
                         byte_matches,word_matches))
    assert(byte_matches~=word_matches,
           'Ambiguous memory share address mode; capture during active gameplay')
    return byte_matches>word_matches and 2 or 1
end

local step=nil
local captured,last_frame=0,-1

local function write_file(name, bytes)
    local file,err=io.open(OUTPUT_DIR..'/'..name,'wb')
    assert(file,err or 'Cannot open output file')
    assert(file:write(bytes))
    assert(file:close())
end

local function serialize_words(share,bytes)
    local result={}
    for i=0,bytes/2-1 do
        result[#result+1]=string.pack('>I2',share:read_u16(i*step))
    end
    return table.concat(result)
end

local function color_bytes(argb)
    return string.char((argb>>16)&255,(argb>>8)&255,argb&255)
end

local function active_palette()
    local result={}
    for i=0,0xbff do
        result[#result+1]=color_bytes(palette:pen_color(palette:pen(i)))
    end
    return table.concat(result)
end

-- MAME's screen_device::pixels(u32*) ALWAYS produces RGB32 even when
-- the underlying screen bitmap is indexed: see src/emu/screen.cpp.
-- Do not look up a second palette entry. Lua screen:pixels() yields a binary
-- host-endian u32 buffer, which '=I4' reads correctly. screen.palette is
-- recorded only as the SOURCE bitmap format, not output encoding.
local function reference_rgb()
    local blob,width,height=screen:pixels()
    assert(width==384 and height==224,
           string.format('Unexpected MAME visible area %sx%s',
                         tostring(width),tostring(height)))
    assert(type(blob)=='string' and #blob==width*height*4,
           'screen:pixels returned malformed 32-bit buffer')
    local indexed=(screen.palette~=nil)
    local result={}
    for i=0,width*height-1 do
        local value=string.unpack('=I4',blob,i*4+1)
        result[#result+1]=color_bytes(value)
    end
    return table.concat(result),indexed and 'indexed_bitmap' or 'rgb_bitmap'
end

local function capture(frame)
    local stem=string.format('frame-%08d',frame)
    write_file(stem..'.gfxram-be.bin',serialize_words(gfx,0x30000))
    write_file(stem..'.cps-a-be.bin',serialize_words(cps_a,0x40))
    write_file(stem..'.cps-b-be.bin',serialize_words(cps_b,0x40))
    write_file(stem..'.palette-rgb24.bin',active_palette())
    local reference,pixel_mode=reference_rgb()
    write_file(stem..'.reference-rgb24.bin',reference)
    write_file(stem..'.manifest.json',string.format([=[{
  "game":"dino","frame":%d,"capture_hook":"frame_done",
  "gfxram_bytes":196608,"cps_a_bytes":64,"cps_b_bytes":64,
  "palette_bytes":9216,"reference_width":384,"reference_height":224,
  "reference_rgb_bytes":258048,"raw_word_endianness":"big",
  "palette_source":"MAME_effective_pen_color",
  "reference_pixel_encoding":"rgb32_resolved",
  "reference_source_format":"%s",
  "obj_latch":"NOT_CAPTURED","pixel_parity_eligible":false,
  "warning":"Authentic MAME RGB only; internal buffered OBJ unavailable"
}
]=],frame,pixel_mode))
    print('[cps1 capture] collected private MAME frame '..tostring(frame)..
          ' ('..pixel_mode..')')
end

-- MAME docs: called after video update. Run from -autoboot_script.
emu.register_frame_done(function()
    if captured>=FRAME_COUNT then return end
    local frame=screen.frame_number
    if frame==last_frame or frame<START_FRAME then return end
    if (frame-START_FRAME)%FRAME_STEP~=0 then return end
    last_frame=frame
    if not step then step=detect_word_step() end
    capture(frame)
    captured=captured+1
end,'frame')
print('[cps1 capture] ready; create directory '..OUTPUT_DIR..
      ' before launching MAME. Requires active dino World 930201.')

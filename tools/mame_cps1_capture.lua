-- dino World 930201: EXPERIMENTAL local-only MAME 0.289 reference capture.
-- Captures original MAME RGB/framebuffer and CPS-1 shared memory.
-- Does NOT capture internal VBlank-latched OBJ; NEVER claim pixel parity.
local OUTPUT_DIR='cps1-captures'
local START_FRAME=900
local FRAME_COUNT=6
local FRAME_STEP=2
-- Same-process source label; not physical VBlank provenance.
local SESSION_ID=os.getenv('CPS1_DINO_CAPTURE_SESSION') or 'UNBOUND'
-- Explicit local opt-in only. The Python launcher strips inherited flags
-- unless --auto-exit-after-capture was requested for the actual game run.
local AUTO_EXIT_FLAG=os.getenv('CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE')
assert(AUTO_EXIT_FLAG==nil or AUTO_EXIT_FLAG=='1',
       'Invalid private MAME auto-exit flag')
local AUTO_EXIT_AFTER_CAPTURE=(AUTO_EXIT_FLAG=='1')
if SESSION_ID~='UNBOUND' then
    assert(#SESSION_ID==32 and SESSION_ID:match('^[0-9a-f]+$'),
           'Invalid private MAME capture session label')
end

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
local last_capture_frame=nil
local exit_scheduled=false
local complete_metadata_streak=0
local AUTO_EXIT_GRACE_FRAMES=120

-- These sizes are mirrored in the Python strict private capture schema.
-- Checking file lengths is strictly a *post-write readiness hint*.
-- It is not content validation or a claim that C++ and Lua represent the
-- same moment. The Python CRC/FNV/session/interval audits remain required.
local READY_FILES={
    {'gfxram-be.bin',196608,196608},
    {'cps-a-be.bin',64,64},
    {'cps-b-be.bin',64,64},
    {'palette-rgb24.bin',9216,9216},
    {'reference-rgb24.bin',258048,258048},
    {'manifest.json',1,16384},
    {'render-regs-be.bin',128,128},
    {'buffered-obj-be.bin',2048,2048},
    {'obj-latch-count.txt',1,128}
}

local function all_capture_files_size_ready()
    -- Probe only existence and length. Never read original frame bytes.
    for index=0,FRAME_COUNT-1 do
        local stem=string.format('frame-%08d',START_FRAME+index*FRAME_STEP)
        for _,rule in ipairs(READY_FILES) do
            local file=io.open(OUTPUT_DIR..'/'..stem..'.'..rule[1],'rb')
            if not file then return false end
            local length=file:seek('end')
            file:close()
            if not length or length<rule[2] or length>rule[3] then
                return false
            end
        end
    end
    return true
end

local function write_file(name, bytes)
    local file,err=io.open(OUTPUT_DIR..'/'..name,'wb')
    assert(file,err or 'Cannot open output file')
    assert(file:write(bytes))
    assert(file:close())
end

-- The multi-frame analyser requires complete CRC32 of all five Lua blobs.
-- This detects accidental damage and swaps, NOT original-game authenticity.
local function crc32(bytes)
    local crc=0xffffffff
    for i=1,#bytes do
        crc=crc ~ bytes:byte(i)
        for _=1,8 do
            local low=crc & 1
            crc=(crc >> 1) ~ (low==1 and 0xedb88320 or 0)
        end
    end
    return string.format('%08x', (~crc) & 0xffffffff)
end

local function refuse_existing(name)
    local file=io.open(OUTPUT_DIR..'/'..name,'rb')
    if file then
        file:close()
        error('Refusing to overwrite existing private MAME capture: '..name)
    end
end

local CAPTURE_COMPONENTS={
    'gfxram-be.bin','cps-a-be.bin','cps-b-be.bin',
    'palette-rgb24.bin','reference-rgb24.bin'
}

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

local function reference_rgb()
    local result={}
    for y=0,223 do
        for x=0,383 do
            local pen=screen:pixel(x,y)
            assert(type(pen)=='number' and pen>=0 and pen<palette.entries,
                   'screen:pixel did not return indexed CPS-1 palette pen')
            result[#result+1]=color_bytes(palette:pen_color(pen))
        end
    end
    return table.concat(result)
end

local function capture(frame)
    local stem=string.format('frame-%08d',frame)
    -- Preflight all six filenames BEFORE any large memory serialization
    -- or disk write. Existing local game data must not be overwritten.
    for _,name in ipairs(CAPTURE_COMPONENTS) do
        refuse_existing(stem..'.'..name)
    end
    refuse_existing(stem..'.manifest.json')

    local captured_files={
        ['gfxram-be.bin']=serialize_words(gfx,0x30000),
        ['cps-a-be.bin']=serialize_words(cps_a,0x40),
        ['cps-b-be.bin']=serialize_words(cps_b,0x40),
        ['palette-rgb24.bin']=active_palette(),
        ['reference-rgb24.bin']=reference_rgb()
    }
    local crc={}
    for _,name in ipairs(CAPTURE_COMPONENTS) do
        crc[name]=crc32(captured_files[name])
        write_file(stem..'.'..name,captured_files[name])
    end

    -- This is the canonical five-file CRC32 schema enforced by the
    -- private MAME sequence analyser. The manifest is written LAST.
    write_file(stem..'.manifest.json',string.format([=[{
  "game":"dino","frame":%d,"capture_hook":"frame_done",
  "capture_session":"%s",
  "gfxram_bytes":196608,"cps_a_bytes":64,"cps_b_bytes":64,
  "palette_bytes":9216,"reference_width":384,"reference_height":224,
  "reference_rgb_bytes":258048,"raw_word_endianness":"big",
  "palette_source":"MAME_effective_pen_color",
  "obj_latch":"NOT_CAPTURED","pixel_parity_eligible":false,
  "file_crc32":{
    "gfxram-be.bin":"%s","cps-a-be.bin":"%s","cps-b-be.bin":"%s",
    "palette-rgb24.bin":"%s","reference-rgb24.bin":"%s"
  },
  "warning":"CRC32 validates Lua files, not callback synchronization or original pixel parity"
}
]=],frame,SESSION_ID,
        crc['gfxram-be.bin'],crc['cps-a-be.bin'],crc['cps-b-be.bin'],
        crc['palette-rgb24.bin'],crc['reference-rgb24.bin']))
    print('[cps1 capture] collected private MAME frame '..tostring(frame))
end

-- MAME docs: called after video update. Run from -autoboot_script.
emu.register_frame_done(function()
    local frame=screen.frame_number
    -- Never stop on frame 910. Two distinct later frame_done callbacks
    -- must observe all 54 expected files with acceptable sizes. This
    -- reduces a premature process shutdown but is not proof that writes
    -- have been fsync'd, are valid, or share actual VBlank provenance.
    -- If a C++ hook failed, exit after a bounded grace interval so the
    -- Python launcher reports an incomplete set instead of timing out.
    if captured>=FRAME_COUNT then
        if AUTO_EXIT_AFTER_CAPTURE and last_capture_frame and
           frame>last_capture_frame and not exit_scheduled then
            if all_capture_files_size_ready() then
                complete_metadata_streak=complete_metadata_streak+1
            else
                complete_metadata_streak=0
            end
            if complete_metadata_streak>=2 then
                exit_scheduled=true
                print('[cps1 capture] complete file-size set observed twice; exiting')
                machine:exit()
            elseif frame>=last_capture_frame+AUTO_EXIT_GRACE_FRAMES then
                exit_scheduled=true
                print('[cps1 capture] C++/Lua file-size set incomplete after grace; exiting for strict local audit')
                machine:exit()
            end
        end
        return
    end
    if frame==last_frame or frame<START_FRAME then return end
    if (frame-START_FRAME)%FRAME_STEP~=0 then return end
    last_frame=frame
    if not step then step=detect_word_step() end
    capture(frame)
    captured=captured+1
    if captured==FRAME_COUNT then last_capture_frame=frame end
end,'frame')
print('[cps1 capture] ready; create directory '..OUTPUT_DIR..
      ' before launching MAME. Requires active dino World 930201.')

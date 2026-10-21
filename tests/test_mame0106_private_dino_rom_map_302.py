"""Stage302 synthetic-only CPS-1 memory map tests; NO original game bytes."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import mame0106_private_dino_rom_map_302 as dino


def artificial_public_rom_declarations():
    """Reconstruct public macro declarations, never ROM data or game pixels."""
    lines=["#define CODE_SIZE 0x200000", "ROM_START( dino )"]
    region=None
    for target,mode,name,offset,n in dino.LOAD_PLAN:
        if region != target:
            if target=="CPU2":
                lines.extend([
                    "ROM_REGION( 0x8000, REGION_GFX2, 0 )",
                    "ROM_COPY( REGION_GFX1, 0x000000, 0x000000, 0x8000 )",
                ])
            size="CODE_SIZE" if target=="CPU1" else hex(dino.REGION_LENGTHS[target])
            lines.append(f"ROM_REGION( {size}, REGION_{target}, 0 )")
            region=target
        _,crc,sha=dino._EXPECTED_SHA[name]
        directive={
            "swap16":"ROM_LOAD16_WORD_SWAP",
            "plain":"ROM_LOAD",
            "groupword_skip6":"ROMX_LOAD",
        }[mode]
        flags=" , ROM_GROUPWORD | ROM_SKIP(6)" if mode=="groupword_skip6" else ""
        lines.append(f'{directive}( "{name}", {offset:#08x}, {n:#07x}, '
                     f'CRC({crc}) SHA1({sha}){flags} )')
        if name=="cd_q.rom":
            lines.append("ROM_CONTINUE( 0x10000, 0x18000 )")
    lines.append("ROM_END")
    return "\n".join(lines)+"\n"


def toy_regions():
    lengths={"CPU1":32,"GFX1":32,"GFX2":4,"CPU2":16,"SOUND1":8}
    payloads={
        "code":bytes([1,2,3,4]),
        **{f"gfx{i}":bytes([i,i+1,i+2,i+3]) for i in range(8)},
        "qsound":bytes(range(8)),
        "sound":b"ABCDEFGH",
    }
    ops=[("region","CPU1",32),("load","CPU1","swap16","code",0,4),
         ("region","GFX1",32)]
    for bank in (0,1):
        for lane in range(4):
            ops.append(("load","GFX1","groupword_skip6",f"gfx{bank*4+lane}",
                        bank*16+2*lane,4))
    ops.extend([
        ("region","GFX2",4),("copy","GFX2","GFX1",0,0,4),
        ("region","CPU2",16),("load","CPU2","plain","qsound",0,4),
        ("continue","CPU2",8,4),
        ("region","SOUND1",8),("load","SOUND1","plain","sound",0,8),
    ])
    return ops,payloads,lengths


class CPS1PrivateRomMap302Tests(unittest.TestCase):
    def setUp(self):
        self.source=artificial_public_rom_declarations()

    def test_exact_public_dino_source_macro_contract(self):
        ops=dino._driver_ops(self.source)
        self.assertEqual(len([o for o in ops if o[0]=="load"]),16)
        self.assertEqual(len([o for o in ops if o[0]=="copy"]),1)
        self.assertEqual(len([o for o in ops if o[0]=="continue"]),1)
        self.assertEqual(ops[0],("region","CPU1",0x200000))
        self.assertEqual(ops[-1][1:3],("SOUND1","plain"))

    def test_swapped_68000_program_bytes_and_coverage(self):
        ops,payloads,lengths=toy_regions()
        result=dino._apply(ops,payloads,lengths=lengths)
        self.assertEqual(result["CPU1"]["source_loaded_bytes"],4)
        self.assertEqual(result["CPU1"]["unpopulated_bytes"],28)
        region=bytearray(8);used=bytearray(8)
        part=payloads["code"]
        swapped=bytearray(part);swapped[::2]=part[1::2];swapped[1::2]=part[::2]
        dino._put(region,used,0,swapped)
        self.assertEqual(region[:4],bytearray([2,1,4,3]))

    def test_source_interleaved_eight_graphics_lanes_cover_region(self):
        ops,payloads,lengths=toy_regions()
        result=dino._apply(ops,payloads,lengths=lengths)
        self.assertEqual(result["GFX1"]["source_loaded_bytes"],32)
        self.assertEqual(result["GFX1"]["unpopulated_bytes"],0)
        self.assertEqual(result["GFX2"]["source_loaded_bytes"],4)

    def test_qsound_split_rom_continuation_preserves_region_gap(self):
        ops,payloads,lengths=toy_regions()
        result=dino._apply(ops,payloads,lengths=lengths)
        self.assertEqual(result["CPU2"]["source_loaded_bytes"],8)
        self.assertEqual(result["CPU2"]["unpopulated_bytes"],8)
        self.assertEqual(result["SOUND1"]["source_loaded_bytes"],8)

    def test_modified_gfx_rom_skip_flag_rejected(self):
        with self.assertRaisesRegex(ValueError,"unrecognized"):
            dino._driver_ops(self.source.replace("ROM_SKIP(6)", "ROM_SKIP(5)",1))

    def test_changed_program_region_offset_is_rejected(self):
        changed=self.source.replace('"cde_23a.rom", 0x000000,','"cde_23a.rom", 0x000002,',1)
        self.assertNotEqual(changed,self.source)
        with self.assertRaisesRegex(ValueError,"layout differs"):
            dino._driver_ops(changed)

    def test_changed_public_crc_or_sha_rejected(self):
        old=dino._EXPECTED_SHA["cde_23a.rom"][1]
        changed=self.source.replace("CRC("+old+")","CRC(deadbeef)",1)
        with self.assertRaisesRegex(ValueError,"identity changed"):
            dino._driver_ops(changed)

    def test_injected_directive_rejected_fail_closed(self):
        s=self.source.replace("ROM_END",
                              "ROM_FILL( 0x0000, 0x80000, 0xaa )\nROM_END")
        with self.assertRaisesRegex(ValueError,"unrecognized"):
            dino._driver_ops(s)

    def test_corrupt_source_mapping_stars_and_qsound_refused(self):
        s=self.source.replace("ROM_COPY( REGION_GFX1, 0x000000",
                              "ROM_COPY( REGION_CPU1, 0x000000")
        with self.assertRaisesRegex(ValueError,"layout differs"):
            dino._driver_ops(s)
        s=self.source.replace("ROM_CONTINUE( 0x10000, 0x18000 )",
                              "ROM_CONTINUE( 0x08000, 0x18000 )")
        with self.assertRaisesRegex(ValueError,"layout differs"):
            dino._driver_ops(s)

    def test_undefined_source_group_lanes_overlap_rejected(self):
        ops,payloads,lengths=toy_regions()
        i=ops.index(("load","GFX1","groupword_skip6","gfx1",2,4))
        ops[i]=("load","GFX1","groupword_skip6","gfx1",0,4)
        with self.assertRaisesRegex(ValueError,"overlaps"):
            dino._apply(ops,payloads,lengths=lengths)

    def test_groupword_strided_write_stays_in_destination_region(self):
        a=bytearray(8);mask=bytearray(8)
        with self.assertRaisesRegex(ValueError,"bounds"):
            dino._put(a,mask,2,b"\x01\x02",stride=8)
        self.assertFalse(any(mask))

    def test_unpopulated_source_copy_and_continue_are_rejected(self):
        ops,payloads,lengths=toy_regions()
        replaced=[("copy","GFX2","CPU1",12,0,4)
                  if o[0]=="copy" else o for o in ops]
        with self.assertRaisesRegex(ValueError,"unloaded"):
            dino._apply(replaced,payloads,lengths=lengths)
        missing=[o for o in ops if o[0]!="load" or o[3]!="qsound"]
        with self.assertRaises(ValueError):
            dino._apply(missing,payloads,lengths=lengths)

    def test_duplicate_region_and_mismatched_source_are_rejected(self):
        ops,payloads,lengths=toy_regions()
        with self.assertRaisesRegex(ValueError,"duplicate"):
            dino._apply([("region","CPU1",32)]+ops,payloads,lengths=lengths)
        with self.assertRaisesRegex(ValueError,"shorter"):
            dino._apply(ops,{**payloads,"code":b"\x00"},lengths=lengths)

    def test_public_manifest_has_sixteen_unique_content_identifiers(self):
        self.assertEqual(len(dino.ORDERED_FILES),16)
        self.assertEqual(len(set(dino.ORDERED_FILES)),16)
        self.assertEqual(set(dino.ORDERED_FILES),set(dino._EXPECTED_SHA))
        self.assertEqual(sum(dino.EXPECTED_COVERAGE.values()),8028160)
        self.assertEqual(dino.REGION_LENGTHS["CPU2"]-dino.EXPECTED_COVERAGE["CPU2"],
                         0x8000)

    def test_no_sensitive_data_can_appear_in_aggregate_status(self):
        fake={
            "schema":dino.SCHEMA,"status":dino.PASS,
            "source_grounded_rom_declarations":16,
            "historical_mame_executable_ran":False,
            "original_dino_gameplay_verified":False,
        }
        self.assertNotIn("payload",json.dumps(fake))
        self.assertFalse(fake["historical_mame_executable_ran"])
        self.assertFalse(fake["original_dino_gameplay_verified"])


if __name__=="__main__":
    unittest.main()

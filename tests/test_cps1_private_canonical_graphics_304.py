"""Stage304: ROM-free tests for canonical Stage299 MAME 0.106 gfx aliases.

Original authorized game ROMs are NEVER fixtures. All 16 invented ZIP
members and SHA1 metadata are synthetic. Full 512-KiB per lane layout
is needed to test actual source C/Python interleave assumptions.
"""
import hashlib
import json
import tempfile
import unittest
import warnings
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from tools import cps1_private_native_tile_parity as native
from tools import cps1_gfx
from tools import mame0106_private_dino_rom_canonicalize_299 as canonical


class CanonicalGfxBridge304Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy_names = tuple(name for name, _ in cps1_gfx.LANES)
        cls.canonical_names = native.CANONICAL_GFX_LANES
        cls.gfx = [
            (bytes((i + 1, 255 - i, i + 3, i + 4)) *
             (cps1_gfx.ROM_SIZE // 4))
            for i in range(8)
        ]
        cls.extra_names = tuple("artificial-other-{}.bin".format(i)
                                for i in range(8))
        cls.extra = [bytes([15 + i]) * (256 + i) for i in range(8)]
        cls.members = dict(zip(cls.canonical_names, cls.gfx))
        cls.members.update(zip(cls.extra_names, cls.extra))
        cls.manifest = tuple(
            (name, len(data), "{:08x}".format(zlib.crc32(data) & 0xffffffff),
             hashlib.sha1(data).hexdigest())
            for name, data in cls.members.items())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino304-rom-free-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic-canonical-dino.zip"
        self.legacy = self.root / "synthetic-legacy-alias.zip"
        self._write_canonical()
        with zipfile.ZipFile(self.legacy, "w", compression=zipfile.ZIP_STORED) as z:
            for name, payload in zip(self.legacy_names, self.gfx):
                z.writestr(name, payload)

    def _write_canonical(self, mutation=None, extra=None, omit=None, duplicate=None):
        with zipfile.ZipFile(self.source, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, payload in self.members.items():
                if name == omit:
                    continue
                if name == mutation:
                    payload = payload[:-1] + bytes([payload[-1] ^ 1])
                z.writestr(name, payload)
            if extra is not None:
                z.writestr(extra, b"synthetic extra ROM")
            if duplicate is not None:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    z.writestr(duplicate, self.members[duplicate])

    def _read(self, path=None):
        with mock.patch.object(canonical, "MANIFEST", self.manifest):
            return native.read_private_gfx(self.source if path is None else path)

    def test_canonical_name_mapping_preserves_original_eight_lane_order(self):
        self.assertEqual(len(self.canonical_names), 8)
        self.assertEqual(tuple(native.LEGACY_TO_CANONICAL),
                         self.legacy_names)
        self.assertEqual(tuple(native.LEGACY_TO_CANONICAL.values()),
                         self.canonical_names)
        self.assertEqual(self.canonical_names[0], "cd_gfx01.rom")
        self.assertEqual(self.canonical_names[4], "cd_gfx05.rom")

    def test_full_synthetic_canonical_rom_hashes_verified_before_assembly(self):
        with mock.patch.object(canonical, "MANIFEST", self.manifest):
            with mock.patch.object(native.canonical, "verify_archive",
                                   wraps=canonical.verify_archive) as checked:
                region = native.read_private_gfx(self.source)
                self.assertEqual(checked.call_count, 1)
        self.assertEqual(len(region), 4 * 1024 * 1024)
        self.assertEqual(region[:8], bytes((
            self.gfx[0][0], self.gfx[0][1],
            self.gfx[1][0], self.gfx[1][1],
            self.gfx[2][0], self.gfx[2][1],
            self.gfx[3][0], self.gfx[3][1],
        )))

    def test_canonical_and_legacy_source_bytes_yield_same_gfx_region(self):
        canon_gfx = self._read()
        legacy_gfx = native.read_private_gfx(self.legacy)
        self.assertEqual(canon_gfx, legacy_gfx)
        self.assertEqual(len(canon_gfx), 0x400000)

    def test_canonical_changed_byte_is_rejected_by_sha1(self):
        self._write_canonical(mutation="cd_gfx07.rom")
        with self.assertRaisesRegex(ValueError, "missing expected"):
            self._read()

    def test_non_gfx_rom_corruption_fails_full_source_hash_gate(self):
        self._write_canonical(mutation=self.extra_names[3])
        with self.assertRaisesRegex(ValueError, "missing expected"):
            self._read()

    def test_canonical_missing_rom_is_rejected(self):
        self._write_canonical(omit=self.extra_names[0])
        with self.assertRaisesRegex(ValueError, "extra or missing"):
            self._read()
        self._write_canonical(omit="cd_gfx03.rom")
        with self.assertRaisesRegex(ValueError, "absent or ambiguous"):
            self._read()

    def test_canonical_extra_rom_is_rejected(self):
        self._write_canonical(extra="suspicious-rom-file.bin")
        with self.assertRaisesRegex(ValueError, "extra or missing"):
            self._read()

    def test_duplicate_canonical_rom_is_rejected(self):
        self._write_canonical(duplicate="cd_gfx05.rom")
        with self.assertRaisesRegex(ValueError, "absent or ambiguous"):
            self._read()

    def test_mixed_legacy_canonical_aliases_fail_closed(self):
        with zipfile.ZipFile(self.source, "a") as z:
            for name, payload in zip(self.legacy_names, self.gfx):
                z.writestr(name, payload)
        with self.assertRaisesRegex(ValueError, "Mixed or ambiguous"):
            self._read()

    def test_canonical_archive_symlink_refused(self):
        alias = self.root / "redirect.zip"
        alias.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self._read(alias)

    def test_legacy_import_still_works_when_original_zip_has_other_members(self):
        with zipfile.ZipFile(self.legacy, "a") as z:
            z.writestr("synthetic-extra-sound.bin", b"synthetic")
        loaded = native.read_private_gfx(self.legacy)
        self.assertEqual(len(loaded), native.GFX_BYTES)

    def test_never_advertise_real_mame_or_switch_parity_from_tile_bytes(self):
        self.assertEqual(native.TILE_COUNT, 32768)
        result = native._report("PRIVATE_DINO_NATIVE_TILE_PARITY_PASSED")
        self.assertFalse(result["mame_gameplay_verified"])
        self.assertFalse(result["switch_pixel_parity_verified"])
        self.assertFalse(result["original_rom_bytes_written_to_disk"])
        self.assertNotIn(str(self.root), json.dumps(result))


if __name__ == "__main__":
    unittest.main()

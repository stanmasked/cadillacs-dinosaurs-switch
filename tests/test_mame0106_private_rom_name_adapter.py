"""Synthetic-only regression cases for the private-content MAME name adapter."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from tools import mame0106_private_rom_name_adapter as p


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.source = self.root / 'input.zip'
        self.xml = self.root / 'source.xml'
        self.a, self.b = b'synthetic-first-record', b'synthetic-second-record-999'
        self.files = {'new-a.bin':self.a, 'new-b.bin':self.b, 'unrelated.txt':b'fake'}
        self.expected = [('old-a.bin',self.a),('old-b.bin',self.b)]
        self.build()

    def build(self):
        with zipfile.ZipFile(self.source,'w') as z:
            for name,data in self.files.items():
                z.writestr(name,data)
        root=ET.Element('mame')
        game=ET.SubElement(root,'game',{'name':'dino','runnable':'yes'})
        for name,data in self.expected:
            ET.SubElement(game,'rom',{'name':name,'size':str(len(data)),
                 'crc':f'{zipfile.crc32(data)&0xffffffff:08x}',
                 'sha1':hashlib.sha1(data).hexdigest()})
        self.xml.write_bytes(ET.tostring(root))
        self.shas=[p.digest_path(self.source),p.digest_path(self.xml)]

    def make(self):
        return p.adapt(source=self.source,driver_xml=self.xml,game='dino',
            expected_source_sha256=self.shas[0],expected_xml_sha256=self.shas[1],
            output_zip=self.root/'out.zip',manifest_json=self.root/'manifest.json')

    def test_exact_relabel_and_manifest(self):
        m=self.make()
        self.assertEqual(m['selected_rom_count'],2)
        with zipfile.ZipFile(self.root/'out.zip') as z:
            self.assertEqual(sorted(z.namelist()), ['old-a.bin','old-b.bin'])
            self.assertEqual(z.read('old-a.bin'),self.a)
            self.assertEqual(z.read('old-b.bin'),self.b)
        self.assertEqual(json.loads((self.root/'manifest.json').read_text())['output_zip_sha256'],p.digest_path(self.root/'out.zip'))

    def test_reproducible_archive(self):
        first=self.make()['output_zip_sha256']
        # Distinct output names, same inputs, deterministic ZIP timestamps and order.
        p.adapt(source=self.source,driver_xml=self.xml,game='dino',
            expected_source_sha256=self.shas[0],expected_xml_sha256=self.shas[1],
            output_zip=self.root/'other.zip',manifest_json=self.root/'other.json')
        self.assertEqual(first,p.digest_path(self.root/'other.zip'))

    def test_wrong_source_pin(self):
        with self.assertRaisesRegex(p.AdapterError,'input_hash_mismatch'):
            p.adapt(source=self.source,driver_xml=self.xml,game='dino',
              expected_source_sha256='0'*64,expected_xml_sha256=self.shas[1],
              output_zip=self.root/'out.zip',manifest_json=self.root/'manifest.json')
        self.assertFalse((self.root/'out.zip').exists())

    def test_missing_content(self):
        self.files.pop('new-a.bin');self.build()
        with self.assertRaisesRegex(p.AdapterError,'missing_or_ambiguous_rom_payload'):
            self.make()

    def test_ambiguous_content(self):
        self.files['copy-of-a.bin']=self.a;self.build()
        with self.assertRaisesRegex(p.AdapterError,'missing_or_ambiguous_rom_payload'):
            self.make()

    def test_bad_or_missing_driver(self):
        with self.assertRaisesRegex(p.AdapterError,'game_driver_missing'):
            p.expected_roms(self.xml,'other')

    def test_unsafe_zip_name(self):
        self.files['../sneaky.bin']=b'a';self.build()
        with self.assertRaisesRegex(p.AdapterError,'unsafe_source_entry'):
            self.make()

    def test_conflicting_destination(self):
        (self.root/'out.zip').write_bytes(b'original keep')
        with self.assertRaisesRegex(p.AdapterError,'output_already_exists'):
            self.make()
        self.assertEqual((self.root/'out.zip').read_bytes(),b'original keep')

    def test_unsupported_xml_checksum(self):
        tree=ET.parse(self.xml)
        tree.find('.//rom').attrib.pop('sha1')
        tree.write(self.xml)
        self.shas[1]=p.digest_path(self.xml)
        with self.assertRaisesRegex(p.AdapterError,'unsupported_driver_rom_entry'):
            self.make()

    def test_corrupt_zip_payload(self):
        self.source.write_bytes(self.source.read_bytes()[:len(self.source.read_bytes())//2])
        self.shas[0]=p.digest_path(self.source)
        with self.assertRaises(p.AdapterError):
            self.make()

    def test_no_private_paths_in_cli_error(self):
        result=p.main(['--source',str(self.source),'--driver-xml',str(self.xml),
            '--source-sha256','0'*64,'--xml-sha256',self.shas[1],
            '--output-zip',str(self.root/'out.zip'),'--manifest',str(self.root/'manifest.json')])
        self.assertEqual(result,1)

if __name__=='__main__':
    unittest.main()
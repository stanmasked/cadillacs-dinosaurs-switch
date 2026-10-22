"""ROM-free regression guard for the pinned NeXium Linux release asset.

No emulator binary is included, downloaded or trusted from mocks.
Only independently compared GitHub release metadata may justify
changing the exact SHA-256, size and immutable release-asset ID.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


SCRIPT=Path('tools/nexium_guest_replay_probe.sh')
EXPECTED_SHA='d96cdd186447eec7a5c05a28fa5aa1b8bb6c8fb85fd7bf76721b349cf2c97dde'
EXPECTED_SIZE=114560520
ASSET_ID=664770154


class NeXiumPinnedReleaseTests(unittest.TestCase):
    def test_public_release_digest_is_statically_pinned(self):
        raw=SCRIPT.read_text(encoding='utf-8')
        self.assertIn(
            'release="https://github.com/nexium-emu/nexium-nightly/releases/'
            'download/nightly/nexium-linux-x86_64.tar.gz"',raw)
        self.assertIn(f'expected="{EXPECTED_SHA}"',raw)
        self.assertIn(f'expected_size={EXPECTED_SIZE}',raw)
        self.assertIn(f'expected_release_asset_id={ASSET_ID}',raw)
        self.assertRegex(EXPECTED_SHA,r'\A[0-9a-f]{64}\Z')

    def test_archive_size_then_sha256_must_fail_closed(self):
        raw=SCRIPT.read_text(encoding='utf-8')
        size_check='wc -c < "$scratch/nexium.tar.gz"'
        sha_check='sha256sum -c -'
        archive_read='tar -tzf "$scratch/nexium.tar.gz"'
        self.assertIn(size_check,raw)
        self.assertIn(sha_check,raw)
        self.assertLess(raw.index(size_check),raw.index(sha_check))
        self.assertLess(raw.index(sha_check),raw.index(archive_read))
        self.assertIn('BLOCKED: emulator release asset size mismatch',raw)
        self.assertIn('BLOCKED: unrecognized emulator release hash',raw)

    def test_fake_truncated_download_never_launches_guest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            stub=root/'curl'
            stub.write_text(
                '#!/bin/sh\n'
                'while [ "$#" -gt 0 ]; do\n'
                '  if [ "$1" = "-o" ]; then\n'
                '    shift\n'
                '    printf BAD_ARCHIVE > "$1"\n'
                '    exit 0\n'
                '  fi\n'
                '  shift\n'
                'done\n'
                'exit 2\n',
                encoding='ascii')
            stub.chmod(0o755)
            nro=root/'test.nro'
            nro.write_bytes(b'ROM-FREE-DIAGNOSTIC-TEST')
            output=root/'report'
            env=os.environ.copy()
            env['PATH']=str(root)+os.pathsep+env.get('PATH','')
            proc=subprocess.run(
                ['bash',str(SCRIPT),str(nro),str(output)],
                env=env,timeout=20,capture_output=True,text=True)
            self.assertEqual(proc.returncode,1)
            self.assertEqual(
                (output/'result.txt').read_text(encoding='ascii').strip(),
                'BLOCKED: emulator release asset size mismatch')
            self.assertFalse((output/'guest-live-counter-hid.csv').exists())
            metadata=(output/'metadata.txt').read_text(encoding='ascii')
            self.assertIn('expected_emulator_sha256='+EXPECTED_SHA,metadata)
            self.assertIn('expected_emulator_bytes='+str(EXPECTED_SIZE),metadata)
            self.assertIn('expected_release_asset_id='+str(ASSET_ID),metadata)


if __name__=='__main__':
    unittest.main()

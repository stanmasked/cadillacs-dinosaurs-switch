"""Stage326: bounded streaming output tests using synthetic shell scripts only."""
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import wolfmame0106_private_binary_gate as gate


class WolfMameProbeOutputCapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="dino326-output-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.exe=self.root/"fake-mame"

    def install(self, body):
        self.exe.write_text("#!/bin/sh\n"+body+"\n",encoding="utf-8")
        self.exe.chmod(self.exe.stat().st_mode|stat.S_IXUSR)

    def test_output_over_cap_is_discarded_without_spooling_to_disk(self):
        self.install("printf '12345678901234567'")
        with patch.object(gate,"MAX_OUTPUT",16), \
             patch.object(gate.tempfile,"TemporaryFile",side_effect=AssertionError("disk spool forbidden")):
            code,output,timed_out=gate.bounded_probe(self.exe,["-help"],self.root,5)
        self.assertEqual(code,0)
        self.assertEqual(output,"")
        self.assertFalse(timed_out)

    def test_small_output_is_returned_without_spooling_to_disk(self):
        self.install("printf 'ok\\n'")
        with patch.object(gate.tempfile,"TemporaryFile",side_effect=AssertionError("disk spool forbidden")):
            code,output,timed_out=gate.bounded_probe(self.exe,["-help"],self.root,5)
        self.assertEqual(code,0)
        self.assertEqual(output,"ok\n")
        self.assertFalse(timed_out)


if __name__ == "__main__":
    unittest.main()

"""Stage325: synthetic process-group cleanup tests; no emulator or ROM."""
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import wolfmame0106_private_binary_gate as gate


def process_is_running(pid):
    try:
        stat_text=Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except FileNotFoundError:
        return False
    except OSError:
        return True
    tail=stat_text.rsplit(")",1)[1].strip().split()
    return not tail or tail[0] != "Z"


def wait_stopped(pid):
    for _ in range(100):
        if not process_is_running(pid):
            return
        time.sleep(0.02)
    raise AssertionError("synthetic probe child remained alive")


class WolfMameProbeProcessGroupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="dino325-probe-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.exe=self.root/"fake-mame"
        self.pidfile=self.root/"child.pid"

    def install_fake(self, exit_immediately):
        tail="exit 0" if exit_immediately else "wait"
        self.exe.write_text(
            "#!/bin/sh\n"
            "sleep 30 &\n"
            "echo \"$!\" > \"$DINO_GATE_CHILD_PID\"\n"
            f"{tail}\n",
            encoding="utf-8",
        )
        self.exe.chmod(self.exe.stat().st_mode | stat.S_IXUSR)

    def child_pid(self):
        self.assertTrue(self.pidfile.is_file())
        return int(self.pidfile.read_text(encoding="ascii").strip())

    def test_timeout_kills_probe_and_background_child(self):
        self.install_fake(exit_immediately=False)
        with patch.dict(os.environ, {"DINO_GATE_CHILD_PID": str(self.pidfile)}):
            code, output, timed_out=gate.bounded_probe(
                self.exe, ["-help"], self.root, 0.2,
            )
        self.assertIsNone(code)
        self.assertEqual(output, "")
        self.assertTrue(timed_out)
        wait_stopped(self.child_pid())

    def test_successful_probe_cleans_background_child_too(self):
        self.install_fake(exit_immediately=True)
        with patch.dict(os.environ, {"DINO_GATE_CHILD_PID": str(self.pidfile)}):
            code, output, timed_out=gate.bounded_probe(
                self.exe, ["-help"], self.root, 5,
            )
        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        self.assertFalse(timed_out)
        wait_stopped(self.child_pid())


if __name__ == "__main__":
    unittest.main()

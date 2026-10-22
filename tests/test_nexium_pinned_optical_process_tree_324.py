"""Stage324 public regressions: mocked process trees only, no ROM or NRO."""
import signal
import subprocess
import unittest
from pathlib import Path
from unittest.mock import call, patch

from tools import nexium_private_pinned_optical_launch_318 as stage


class Stage324PinnedOpticalProcessTree(unittest.TestCase):
    def test_wrapper_timeout_exceeds_the_runner_hard_cap(self):
        # The shell runner has a 190-second cap; keep cleanup margin above it.
        self.assertEqual(stage.RUN_TIMEOUT_SECONDS, 220)
        self.assertGreater(stage.RUN_TIMEOUT_SECONDS, 190)

    def test_timeout_terminates_descendants_and_runner_process_group(self):
        class Proc:
            pid = 45100
            def wait(self, timeout=None):
                if timeout == 0.01:
                    raise subprocess.TimeoutExpired("private-runner", timeout)
                return 0
            def poll(self):
                return 0

        proc = Proc()
        command = ["bash", "mock-private-runner"]
        cwd = Path("/mock/private-root")
        with patch.object(stage.subprocess, "Popen", return_value=proc) as popen, \
             patch.object(stage, "_descendant_pids", return_value=[45101]) as descendants, \
             patch.object(stage.os, "kill") as kill, \
             patch.object(stage.os, "killpg") as killpg:
            with self.assertRaisesRegex(ValueError, "bounded private X11 run failed"):
                stage._execute_bounded(command, cwd=cwd, timeout=0.01)

        popen.assert_called_once_with(
            command, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            start_new_session=True)
        self.assertEqual(descendants.call_count, 2)
        self.assertEqual(kill.call_args_list, [
            call(45101, signal.SIGTERM),
            call(45101, signal.SIGKILL),
        ])
        self.assertEqual(killpg.call_args_list, [
            call(45100, signal.SIGTERM),
            call(45100, signal.SIGKILL),
        ])

    def test_success_still_cleans_any_remaining_helper_processes(self):
        class Proc:
            pid = 45110
            def wait(self, timeout=None):
                return 0
            def poll(self):
                return 0

        proc = Proc()
        command = ["bash", "mock-private-runner"]
        cwd = Path("/mock/private-root")
        with patch.object(stage.subprocess, "Popen", return_value=proc), \
             patch.object(stage, "_descendant_pids", return_value=[45111]), \
             patch.object(stage.os, "kill") as kill, \
             patch.object(stage.os, "killpg") as killpg:
            result = stage._execute_bounded(command, cwd=cwd, timeout=1)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(kill.call_args_list, [
            call(45111, signal.SIGTERM),
            call(45111, signal.SIGKILL),
        ])
        self.assertEqual(killpg.call_args_list, [
            call(45110, signal.SIGTERM),
            call(45110, signal.SIGKILL),
        ])

    def test_spawn_error_is_redacted(self):
        secret = "/private/user/session/ne-xium"
        with patch.object(stage.subprocess, "Popen", side_effect=OSError(secret)):
            with self.assertRaises(ValueError) as ctx:
                stage._execute_bounded(["bash", secret], cwd=Path("/mock"))
        self.assertNotIn(secret, str(ctx.exception))
        self.assertEqual(str(ctx.exception), "bounded private X11 run failed")


if __name__ == "__main__":
    unittest.main()

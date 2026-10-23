"""Stage337 tests for the external Wine launcher adapter."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "wolfmame0106_private_wine_external_wrapper.sh"


class ExternalWineWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stage337-wine-wrapper-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wrapper = self.root / "private-wrapper.sh"
        self.wrapper.write_bytes(SOURCE.read_bytes())
        self.wrapper.chmod(0o700)
        self.launcher = self.root / "guarded-launcher.sh"
        self.launcher.write_text("#!/bin/sh\nprintf '<%s>\\n' \"$@\"\n")
        self.launcher.chmod(0o700)

    def run_wrapper(self, *args, launcher=None):
        env = os.environ.copy()
        env.pop("REPO_WINE_LAUNCHER", None)
        if launcher is not None:
            env["REPO_WINE_LAUNCHER"] = str(launcher)
        return subprocess.run(
            [str(self.wrapper), *args],
            text=True, capture_output=True, env=env, timeout=5,
        )

    def test_forwards_arguments_without_rewriting(self):
        result = self.run_wrapper(
            "-verifyroms", "dino", "-rompath", "/private/roms",
            launcher=self.launcher,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "<-verifyroms>\n<dino>\n<-rompath>\n</private/roms>\n",
        )

    def test_missing_launcher_environment_fails_closed(self):
        result = self.run_wrapper("-help")
        self.assertEqual(result.returncode, 64)
        self.assertIn("REPO_WINE_LAUNCHER must name", result.stderr)

    def test_relative_launcher_path_is_rejected(self):
        result = self.run_wrapper("-help", launcher=Path("relative-launcher.sh"))
        self.assertEqual(result.returncode, 64)
        self.assertIn("absolute path", result.stderr)

    def test_missing_launcher_is_rejected(self):
        missing = self.root / "missing-launcher.sh"
        result = self.run_wrapper("-help", launcher=missing)
        self.assertEqual(result.returncode, 64)
        self.assertIn("regular file", result.stderr)

    def test_symlink_launcher_is_rejected(self):
        link = self.root / "launcher-link.sh"
        link.symlink_to(self.launcher)
        result = self.run_wrapper("-help", launcher=link)
        self.assertEqual(result.returncode, 64)
        self.assertIn("must not be a symlink", result.stderr)


if __name__ == "__main__":
    unittest.main()

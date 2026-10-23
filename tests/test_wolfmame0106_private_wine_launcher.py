"""Stage333 tests for the local-only Wine launcher; never use game assets."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "wolfmame0106_private_wine_launcher.sh"


@unittest.skipIf(os.name == "nt", "the launcher targets POSIX Wine hosts")
class PrivateWineLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stage333-wine-launcher-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mame = self.root / "mame0106.exe"
        self.mame.write_bytes(b"MZ synthetic placeholder; not a real executable")
        self.fake_wine = self.root / "fake-wine"
        self.args_file = self.root / "args.txt"
        self.env_file = self.root / "env.txt"
        self.fake_wine.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$@\" > \"$WINE_CAPTURE_ARGS\"\n"
            "printf '%s\\n' \"$WINEPREFIX|$WINEARCH|$WINEDEBUG\" > \"$WINE_CAPTURE_ENV\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        self.fake_wine.chmod(0o700)
        self.prefix = self.root / "prefix"
        self.env = {
            **os.environ,
            "MAME0106_EXE": str(self.mame),
            "WINE_BIN": str(self.fake_wine),
            "WINEPREFIX": str(self.prefix),
            "WINE_CAPTURE_ARGS": str(self.args_file),
            "WINE_CAPTURE_ENV": str(self.env_file),
        }

    def run_launcher(self, *args, env=None):
        return subprocess.run(
            [str(LAUNCHER), *args],
            cwd=ROOT,
            env=self.env if env is None else env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )

    def test_forwards_absolute_mame_and_arguments(self):
        result = self.run_launcher("-help", "-showconfig")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.args_file.read_text(encoding="utf-8").splitlines(),
            [str(self.mame), "-help", "-showconfig"],
        )
        self.assertEqual(
            self.env_file.read_text(encoding="utf-8").strip(),
            f"{self.prefix}|win32|-all",
        )
        self.assertTrue(self.prefix.parent.is_dir())

    def test_refuses_mame_inside_repository(self):
        env = {**self.env, "MAME0106_EXE": str(LAUNCHER)}
        result = self.run_launcher("-help", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the repository", result.stderr)
        self.assertFalse(self.args_file.exists())

    def test_refuses_symlink_mame_path(self):
        link = self.root / "mame-link.exe"
        link.symlink_to(self.mame)
        env = {**self.env, "MAME0106_EXE": str(link)}
        result = self.run_launcher("-help", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not be a symlink", result.stderr)
        self.assertFalse(self.args_file.exists())

    def test_refuses_relative_mame_path(self):
        env = {**self.env, "MAME0106_EXE": "mame0106.exe"}
        result = self.run_launcher("-help", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute path", result.stderr)
        self.assertFalse(self.args_file.exists())

    def test_refuses_prefix_inside_repository(self):
        env = {**self.env, "WINEPREFIX": str(ROOT / ".stage333-forbidden-prefix")}
        result = self.run_launcher("-help", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the repository", result.stderr)
        self.assertFalse(self.args_file.exists())

    def test_missing_mame_path_fails_closed(self):
        env = dict(self.env)
        env.pop("MAME0106_EXE")
        result = self.run_launcher("-help", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MAME0106_EXE", result.stderr)
        self.assertFalse(self.args_file.exists())


if __name__ == "__main__":
    unittest.main()

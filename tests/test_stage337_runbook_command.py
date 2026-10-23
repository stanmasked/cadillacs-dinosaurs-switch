"""Static regression tests for the Stage337 private replay runbook/runtime bundle."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "stage335-wine32-smoke-and-private-replay.md"
WINE_WORKFLOW = ROOT / ".github" / "workflows" / "wine32-offline-runtime.yml"
SLASH = chr(92)


class Stage337RunbookTests(unittest.TestCase):
    def test_capture_command_has_valid_shell_continuations(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        lines = text.splitlines()
        start = next(i for i, line in enumerate(lines)
                     if line.startswith("python3 tools/wolfmame0106_private_mng_capture.py"))
        command = []
        for line in lines[start:]:
            if line == chr(96) * 3:
                break
            command.append(line)
        self.assertGreaterEqual(len(command), 8)
        self.assertTrue(command[0].startswith("python3 "))
        self.assertTrue(command[-1].strip().startswith("--out "))
        for line in command[:-1]:
            self.assertTrue(line.endswith(SLASH), f"missing continuation: {line!r}")
            self.assertFalse(line.endswith(SLASH * 2),
                             f"double slash breaks continuation: {line!r}")
        result = subprocess.run(
            ["sh", "-n"], input="\n".join(command) + "\n",
            text=True, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_offline_wine_bundle_includes_both_preloaders(self):
        text = WINE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("wine32-preloader:i386", text)
        self.assertIn("wine64-preloader:amd64", text)
        self.assertIn("test -x /usr/lib/wine/wine-preloader", text)
        self.assertIn("test -x /usr/lib/wine/wine64-preloader", text)
        self.assertIn("Offline Wine bundle is missing a required preloader package", text)

    def test_workflow_registers_qemu_before_wineboot(self):
        text = WINE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("options: --cap-add=SYS_ADMIN", text)
        mount_at = text.index("mount -t binfmt_misc binfmt_misc /tmp/bfmt-qemu")
        register_at = text.index('> /tmp/bfmt-qemu/register')
        enabled_at = text.index('test "$(head -1 /tmp/bfmt-qemu/qemu-i386)" = enabled')
        wineboot_at = text.index("WINEPREFIX=\\"$WINEPREFIX\\" WINEARCH=win32 WINEDEBUG=-all wineboot -u")
        self.assertLess(mount_at, register_at)
        self.assertLess(register_at, enabled_at)
        self.assertLess(enabled_at, wineboot_at)


if __name__ == "__main__":
    unittest.main()

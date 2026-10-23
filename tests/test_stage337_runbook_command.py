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
        self.assertIn("options: --cap-add=SYS_ADMIN --security-opt seccomp=unconfined --security-opt apparmor=unconfined", text)
        mount_at = text.index("mount -t binfmt_misc binfmt_misc /tmp/bfmt-qemu")
        register_at = text.index('> /tmp/bfmt-qemu/register')
        enabled_at = text.index('test "$(head -1 /tmp/bfmt-qemu/qemu-i386)" = enabled')
        wineboot_at = text.index('WINEPREFIX="$WINEPREFIX" WINEARCH=win32 WINEDEBUG=-all wineboot -u')
        self.assertLess(mount_at, register_at)
        self.assertLess(register_at, enabled_at)
        self.assertLess(enabled_at, wineboot_at)


    def test_qemu_binfmt_magic_uses_printf_hex_escapes(self):
        text = WINE_WORKFLOW.read_text(encoding="utf-8")
        line = next(line for line in text.splitlines()
                    if "printf ':qemu-i386:M::" in line)
        self.assertIn(r"M::\x7fELF\x01\x01\x01\x00::%s:OCF\n", line)
        self.assertNotIn(r"M::\\x7fELF", line)


    def test_qemu_binfmt_printf_emits_exact_binary_magic(self):
        text = WINE_WORKFLOW.read_text(encoding="utf-8")
        line = next(line for line in text.splitlines()
                    if "printf ':qemu-i386:M::" in line)
        fmt = line.split("printf ", 1)[1].split("'", 2)[1]
        result = subprocess.run(
            ["bash", "-c", 'printf "$1" "$2"', "stage345", fmt,
             "/private/qemu-i386-static"],
            check=True, capture_output=True, timeout=5,
        )
        self.assertEqual(
            result.stdout,
            b":qemu-i386:M::\x7fELF\x01\x01\x01\x00::/private/qemu-i386-static:OCF\n",
        )


    def test_listxml_probe_is_bounded_and_emits_summary_only(self):
        text = WINE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("90s xvfb-run -a sh", text)
        self.assertNotIn("180s xvfb-run -a sh", text)
        self.assertIn("listxml_status=0", text)
        self.assertIn("stdout_bytes=", text)
        self.assertIn("dino_driver_present=", text)
        self.assertIn("stage348-listxml-diagnostic.txt", text)
        self.assertIn("if: always()", text)
        self.assertIn("if-no-files-found: ignore", text)
        self.assertIn('write_text("\\n".join(report)', text)
        self.assertIn("stderr_tail_begin", text)
        self.assertNotIn("path: /tmp/stage333-mame-driver.xml", text)
        self.assertNotIn("retention-days: 7", text)
        self.assertIn("Clean ephemeral runtime material", text)
        self.assertIn("if: always()", text)
        self.assertIn('rm -f /tmp/stage333-mame-driver.xml /tmp/stage333-mame-stderr.txt', text)
        self.assertIn("wineboot_status=0", text)
        self.assertIn("90s xvfb-run -a env", text)
        self.assertIn("stage352-wineboot-diagnostic.txt", text)
        self.assertIn("Upload ROM-free Stage352 Wineboot diagnostic", text)
        self.assertIn("|| wineboot_status=$?", text)
        self.assertIn("umount /tmp/bfmt-qemu 2>/dev/null || true", text)
        self.assertLess(text.index("umount /tmp/bfmt-qemu"), text.index("rm -rf /tmp/stage332-mame /tmp/stage332-romfree-wine /tmp/wine-debs /tmp/bfmt-qemu"))
        self.assertEqual(text.count("retention-days: 3"), 7)
        self.assertIn("Split offline Wine32 package bundle into size-bounded parts", text)
        self.assertIn("split -b 200M -d -a 2 /tmp/wine32-offline.tar", text)
        self.assertIn("256 * 1024 * 1024", text)
        self.assertIn("parts-manifest.tsv", text)
        self.assertIn("parts.sha256", text)
        self.assertIn("archive.sha256", text)
        self.assertIn("README-transfer.txt", text)
        self.assertNotIn("name: wine32-debian-trixie-offline-packages", text)
        for suffix in ("00", "01", "02", "03"):
            self.assertIn(f"name: wine32-debian-trixie-offline-part-{suffix}", text)
            self.assertIn(f"if: success() && hashFiles('wine32-offline-transfer/wine32-offline.tar.part-{suffix}') != ''", text)
        self.assertIn("rm -f /tmp/wine32-offline.tar", text)
        self.assertIn('"$GITHUB_WORKSPACE/wine32-offline-transfer"', text)


if __name__ == "__main__":
    unittest.main()

"""Stage401 checks for deterministic Wine DLL search-path setup."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "wolfmame0106_private_wine_launcher.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "wine32-offline-runtime.yml"


class WineDllPathWorkflowTests(unittest.TestCase):
    def test_launcher_discovers_debian_multiarch_directories_only_as_fallback(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        start = source.index('if [ -z "${WINEDLLPATH:-}" ]; then')
        end = source.index('\nfi\n\nexec "$wine_bin"', start)
        block = source[start:end]
        self.assertIn('/usr/lib/i386-linux-gnu/wine/i386-unix', block)
        self.assertIn('/usr/lib/x86_64-linux-gnu/wine/x86_64-unix', block)
        self.assertIn('/usr/lib/i386-linux-gnu/wine', block)
        self.assertIn('/usr/lib/x86_64-linux-gnu/wine', block)
        self.assertIn('export WINEDLLPATH="$wine_dllpath"', block)

    def test_explicit_caller_dllpath_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mame = root / "mame0106.exe"
            mame.write_bytes(b"ROM-free test placeholder")
            prefix = root / "wine-prefix"
            prefix.mkdir()
            fake_wine = root / "fake-wine.sh"
            fake_wine.write_text(
                '#!/bin/sh\nprintf "WINEDLLPATH=%s\\n" "${WINEDLLPATH-<unset>}"\n'
                'printf "ARG=%s\\n" "$@"\n',
                encoding="utf-8",
            )
            fake_wine.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "MAME0106_EXE": str(mame),
                "WINEPREFIX": str(prefix),
                "WINE_BIN": str(fake_wine),
                "WINEDLLPATH": "caller-selected-path",
                "WINEARCH": "win32",
                "WINEDEBUG": "-all",
            })
            result = subprocess.run(
                ["sh", str(LAUNCHER), "-help"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WINEDLLPATH=caller-selected-path", result.stdout)
            self.assertIn(f"ARG={mame}", result.stdout)
            self.assertIn("ARG=-help", result.stdout)

    def test_wine32_workflow_sets_dllpath_before_bootstrap_and_mame_probes(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        start = source.index("      - name: Stage333 ROM-free Wine32 launcher audit")
        end = source.index("      - name: Stage356 native Wine64 fallback audit", start)
        block = source[start:end]
        dllpath = "export WINEDLLPATH=/usr/lib/i386-linux-gnu/wine:/usr/lib/x86_64-linux-gnu/wine"
        self.assertIn(dllpath, block)
        self.assertLess(block.index(dllpath), block.index("wineboot -u"))
        self.assertLess(block.index(dllpath), block.index("wolfmame0106_private_wine_launcher.sh -help"))

    def test_wine64_fallback_keeps_dllpath_exported(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        start = source.index("      - name: Stage356 native Wine64 fallback audit")
        end = source.index("      - name: Upload ROM-free Stage348 listxml diagnostic summary", start)
        block = source[start:end]
        self.assertIn(
            "export WINEDLLPATH=/usr/lib/i386-linux-gnu/wine:/usr/lib/x86_64-linux-gnu/wine",
            block,
        )


if __name__ == "__main__":
    unittest.main()

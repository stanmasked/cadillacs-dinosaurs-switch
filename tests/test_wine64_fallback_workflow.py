"""Stage397 regression checks for the Wine64 fallback bootstrap command."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "wine32-offline-runtime.yml"


class Wine64FallbackWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = WORKFLOW.read_text(encoding="utf-8")
        start = source.index("      - name: Stage356 native Wine64 fallback audit")
        end = source.index("      - name: Upload ROM-free Stage348 listxml diagnostic summary", start)
        cls.block = source[start:end]

    def test_bootstrap_invokes_native_wine64_loader_directly(self):
        self.assertIn("wineboot_exe_status=skipped", self.block)
        self.assertIn(
            "wineboot_exe=$(find /usr/lib/x86_64-linux-gnu/wine /usr/lib/wine "
            "-path '*/x86_64-windows/wineboot.exe' -type f -print -quit "
            "2>/dev/null || true)",
            self.block,
        )
        self.assertIn(
            'WINELOADER="$wine64_bin" WINEDLLPATH="$wine64_dllpath" '
            '"$wine64_bin" "$wineboot_exe" -u',
            self.block,
        )
        self.assertIn("wineboot_invocation=direct_native_wine64_loader", self.block)
        self.assertIn('export WINELOADER="$wine64_bin"', self.block)
        self.assertIn(
            "export WINEDLLPATH=/usr/lib/i386-linux-gnu/wine:/usr/lib/x86_64-linux-gnu/wine",
            self.block,
        )

    def test_bootstrap_does_not_use_debian_wineboot_wrapper(self):
        self.assertNotIn("WINEARCH=win64 WINEDEBUG=-all wineboot -u", self.block)
        self.assertNotIn("xvfb-run -a env WINEPREFIX=\"$WINEPREFIX\" WINEARCH=win64 "
                         "WINEDEBUG=-all wineboot -u", self.block)

    def test_missing_native_bootstrap_is_a_failure(self):
        self.assertIn("wineboot_exe_status=missing", self.block)
        self.assertIn('elif [ "$wineboot_exe_status" != found ]; then fallback_status=127', self.block)


if __name__ == "__main__":
    unittest.main()

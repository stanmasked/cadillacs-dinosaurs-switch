"""ROM-free regression of the opt-in upstream MAME 0.289 build recipe.

Checks safety boundaries and the exact pinned official subtarget build
command. An actual full-tree MAME compilation runs only on GitHub Actions.
"""
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mame0289-cps1-build.yml"


class Mame0289BuildRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipe = WORKFLOW.read_text(encoding="utf-8")

    def test_only_explicit_workflow_changes_or_manual_runs_start_build(self):
        self.assertIn("workflow_dispatch:", self.recipe)
        self.assertIn("'.github/workflows/mame0289-cps1-build.yml'", self.recipe)
        self.assertNotIn("  pull_request:", self.recipe)
        self.assertIn("timeout-minutes: 55", self.recipe)

    def test_upstream_checkout_pins_exact_known_mame0289_tag_commit(self):
        self.assertIn("MAME_COMMIT: f34f02505e32c1993c6a782b6814232cbfc74e36",
                      self.recipe)
        self.assertIn("MAME_TAG: mame0289", self.recipe)
        self.assertIn("https://github.com/mamedev/mame.git", self.recipe)
        self.assertIn('rev-parse HEAD', self.recipe)
        self.assertIn('"$MAME_COMMIT"', self.recipe)

    def test_actual_mame_source_replaces_only_temporary_video_file(self):
        self.assertIn("python3 tools/mame_obj_source_probe.py", self.recipe)
        self.assertIn("python3 tools/mame_obj_real_source_audit.py", self.recipe)
        self.assertIn("src/mame/capcom/cps1_v.cpp", self.recipe)
        self.assertIn("cp \"$generated\" \"$original\"", self.recipe)
        self.assertIn("diff --name-only", self.recipe)

    def test_real_subtarget_build_requires_its_full_dependency_tree(self):
        self.assertIn("make -j2 SUBTARGET=dino", self.recipe)
        self.assertIn("SOURCES=src/mame/capcom/cps1.cpp", self.recipe)
        self.assertIn("REGENIE=1", self.recipe)
        self.assertIn("libsdl2-dev", self.recipe)
        self.assertIn("libsdl2-ttf-dev", self.recipe)
        self.assertIn("qt6-base-dev", self.recipe)

    def test_never_collects_game_assets_or_publishes_modified_emulator(self):
        self.assertIn("permissions:\n  contents: read", self.recipe)
        self.assertNotIn("upload-artifact@", self.recipe)
        self.assertNotIn("ROM_START(", self.recipe)
        self.assertIn('mame_dino_binary_verify.py', self.recipe)
        self.assertIn('"$binary" "$RUNNER_TEMP/mame0289"', self.recipe)


if __name__ == "__main__":
    unittest.main()

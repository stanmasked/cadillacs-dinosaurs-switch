"""Stage311: ROM-free regressions for Switch SD diagnostics bootstrap order.

The actual NRO is compiled separately by the Switch CI. These source-level
tests establish that SD mounting is reachable in the normal diagnostic path
rather than only in the optional arena selftest branch.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "source" / "main.c"


class Stage311SwitchSdMountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")
        cls.entry = cls.source.split("int main(int argc, char **argv) {", 1)[1]

    def test_mount_occurs_once_and_before_gfx_probe(self):
        self.assertEqual(self.entry.count("(void)fsdevMountSdmc();"), 1)
        mount_at = self.entry.index("(void)fsdevMountSdmc();")
        gfx_at = self.entry.index("uint8_t *gfx=load_region();")
        self.assertLess(mount_at, gfx_at)

    def test_sd_mount_runs_in_release_and_emulator_paths(self):
        entry = self.entry
        mount_at = entry.index("(void)fsdevMountSdmc();")
        self.assertLess(mount_at, entry.index("#ifdef DINO_EMULATOR_SELFTEST"))
        self.assertLess(mount_at, entry.index("bool arena_active=(gfx==NULL);"))
        self.assertLess(mount_at, entry.index("Cps1Sequence sequence={0};"))

    def test_sequence_attempt_happens_after_mount_and_gfx(self):
        entry = self.entry
        for key in ("load_sequence_image(gfx,&scene,&sequence,&sequence_blob)",
                    "load_scene_image(gfx,&scene)"):
            self.assertLess(entry.index("(void)fsdevMountSdmc();"),
                            entry.index(key))
            self.assertLess(entry.index("uint8_t *gfx=load_region();"),
                            entry.index(key))
        self.assertIn("if (gfx) {", entry)
        self.assertIn("if (!scene_rgba) scene_rgba=load_scene_image(gfx,&scene);",
                      entry)

    def test_fallback_does_not_require_original_graphics(self):
        entry = self.entry
        self.assertIn("bool arena_active=(gfx==NULL);", entry)
        self.assertIn("bool show_scene=(sequence_blob!=NULL);", entry)
        self.assertIn("if (arena_active) (void)dino_switch_sound_open();", entry)

    def test_all_asset_paths_match_stage310_staging_layout(self):
        text = self.source
        for filename in ("gfx.bin", "sequence.bin"):
            self.assertIn('"sdmc:/switch/cadillacs-dinosaurs-switch/' +
                          filename + '"', text)
        self.assertIn('"sdmc:/switch/cadillacs-dinosaurs-switch/scene.bin"', text)

    def test_mount_not_pushed_inside_the_selftest_only_branch(self):
        entry = self.entry
        line_before_mount = entry[:entry.index("(void)fsdevMountSdmc();")]
        self.assertNotIn("#ifdef DINO_EMULATOR_SELFTEST", line_before_mount)
        self.assertNotIn("if (arena_active) {", line_before_mount)
        # Avoid duplicate mounting of the same devoptab, regardless of whether
        # libnx homebrew has already mounted sdmc automatically.
        self.assertEqual(len(re.findall(r"\bfsdevMountSdmc\s*\(", entry)), 1)


if __name__ == "__main__":
    unittest.main()

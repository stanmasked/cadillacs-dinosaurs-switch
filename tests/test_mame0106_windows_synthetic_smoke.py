"""Static ROM-free assertions for synthetic-only Windows behavior coverage."""
import os
import unittest
from unittest.mock import patch
from tools import mame0106_windows_synthetic_smoke as p
from tools.mame0106_private_windows_capsule import POWERSHELL

class WindowsSyntheticFixtureTests(unittest.TestCase):
    def test_hard_pins_and_guard_isolated_in_fixture_only(self):
        out=p.synthetic_copy('1'*64,'2'*64,'3'*64)
        self.assertIn('1'*64,out)
        self.assertIn('2'*64,out)
        self.assertIn('3'*64,out)
        self.assertIn(p.GUARD,POWERSHELL)
        self.assertNotIn(p.GUARD,out)
        self.assertIn(p.PRODUCTION_SUCCESS,POWERSHELL)
        self.assertNotIn(p.PRODUCTION_SUCCESS,out)
        self.assertIn(p.SYNTHETIC_SUCCESS,out)

    def test_fixture_is_never_rom(self):
        self.assertIn(b'SYNTHETIC',p.FAKE_ROM)
        self.assertIn(b'NOT GAME ROM',p.FAKE_ROM)
        self.assertIn('synthetic_stub.cs',p.run.__code__.co_consts)

    def test_windows_host_only_and_fail_closed_in_linux(self):
        with patch.object(p.sys,'platform','linux'):
            with self.assertRaisesRegex(p.SyntheticSmokeError,'requires_public_windows_synthetic_runner'):
                p.run()

    def test_guard_production_has_exclusive_early_exit(self):
        self.assertEqual(POWERSHELL.count(p.GUARD),1)
        self.assertLess(POWERSHELL.index(p.GUARD),POWERSHELL.index('capsule.json'))

    def test_synthetic_refuses_unknown_production_template(self):
        with patch.object(p,'POWERSHELL','no matching guards'):
            with self.assertRaisesRegex(p.SyntheticSmokeError,'unexpected_production_script_structure'):
                p.synthetic_copy('1'*64,'2'*64,'3'*64)

if __name__ == '__main__':
    unittest.main()

"""Stage319: reject X11 windows from unrelated/stale emulator processes."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from tools import nexium_x11_process_window_319 as windows


def ppid_from(mapping):
    def parent(pid):
        if pid not in mapping:
            raise OSError("synthetic process missing")
        return mapping[pid]
    return parent


def fake_xdotool(ids="", owners=None, status=0):
    owners=owners or {}
    commands=[]
    def runner(argv,**kwargs):
        commands.append(tuple(argv))
        assert kwargs["timeout"]==3
        if argv[1]=="search":
            return SimpleNamespace(returncode=status,stdout=ids)
        if argv[1]=="getwindowpid":
            info=owners.get(argv[2],None)
            if info is None:
                return SimpleNamespace(returncode=1,stdout="")
            return SimpleNamespace(returncode=0,stdout=str(info)+"\n")
        raise AssertionError("unexpected command")
    return runner,commands


class Stage319WindowOwnerTests(unittest.TestCase):
    def test_current_process_and_exact_emulator_owner(self):
        self.assertTrue(windows.belongs_to_run(
            os.getpid(),os.getpid(),parent_for=lambda x:1))
        runner,calls=fake_xdotool("145\n",{"145":6400})
        self.assertEqual(
            windows.window_for_process(6400,runner=runner,
                                       parent_for=ppid_from({})),
            "145")
        self.assertEqual(calls[0][1],"search")
        self.assertEqual(calls[1][1],"getwindowpid")

    def test_exact_descendant_accepted_and_unrelated_window_discarded(self):
        tree=ppid_from({6410:6400,6420:6410,7200:1})
        runner,calls=fake_xdotool("99\n100\n",
                                  {"99":7200,"100":6420})
        self.assertEqual(windows.window_for_process(
            6400,runner=runner,parent_for=tree),"100")

    def test_old_ne_xium_window_with_identical_title_does_not_count(self):
        runner,calls=fake_xdotool("1234\n",{"1234":55})
        self.assertIsNone(windows.window_for_process(
            6400,runner=runner,parent_for=ppid_from({55:20,20:1})))

    def test_no_client_process_id_is_fail_closed(self):
        runner,calls=fake_xdotool("72\n",{})
        self.assertIsNone(windows.window_for_process(
            6400,runner=runner,parent_for=ppid_from({})))

    def test_two_matching_windows_are_ambiguous(self):
        runner,calls=fake_xdotool("72\n73\n",
                                  {"72":6400,"73":6410})
        self.assertIsNone(windows.window_for_process(
            6400,runner=runner,parent_for=ppid_from({6410:6400})))

    def test_duplicate_xid_does_not_create_false_ambiguity(self):
        runner,calls=fake_xdotool("72\n72\n",{"72":6400})
        self.assertEqual(windows.window_for_process(
            6400,runner=runner,parent_for=ppid_from({})),"72")
        self.assertEqual(len(calls),2)

    def test_malformed_xid_and_client_pid_rejected(self):
        for item in ("bad", "-17", "7.2", "123x"):
            runner,_=fake_xdotool(item+"\n",{"123":6400})
            with self.subTest(raw=item):
                self.assertIsNone(windows.window_for_process(
                    6400,runner=runner,parent_for=ppid_from({})))
        runner,_=fake_xdotool("72\n",{"72":"bob"})
        self.assertIsNone(windows.window_for_process(
            6400,runner=runner,parent_for=ppid_from({})))

    def test_search_fails_and_extra_window_list_blocked(self):
        runner,_=fake_xdotool("72\n",{"72":6400},status=1)
        self.assertIsNone(windows.window_for_process(
            6400,runner=runner,parent_for=ppid_from({})))
        runner,_=fake_xdotool("72\n"*(windows.WINDOW_LIMIT+1),
                              {"72":6400})
        self.assertIsNone(windows.window_for_process(
            6400,runner=runner,parent_for=ppid_from({})))
        runner,_=fake_xdotool("9"*5000,{"9":6400})
        self.assertIsNone(windows.window_for_process(
            6400,runner=runner,parent_for=ppid_from({})))

    def test_missing_xdotool_is_not_a_host_proof(self):
        def unavailable(*a,**k):
            raise FileNotFoundError("xdotool not installed")
        self.assertIsNone(windows.window_for_process(6400,runner=unavailable))

    def test_cyclic_ancestor_chain_cannot_be_proven(self):
        self.assertFalse(windows.belongs_to_run(
            6410,6400,parent_for=ppid_from({6410:6420,6420:6410})))

    def test_empty_or_invalid_pid_input_rejected(self):
        for owner,root in ((0,6400),(-1,6400),(True,6400),
                           ("6400",6400),(6400,True),(6400,0)):
            with self.subTest(owner=owner,root=root):
                self.assertFalse(windows.belongs_to_run(
                    owner,root,parent_for=lambda pid:pid-1))
        self.assertIsNone(windows.window_for_process(
            True,runner=lambda *args,**kwargs:None))

    def test_bounded_parent_chain_requires_actual_root(self):
        chain={9000+i:9001+i for i in range(35)}
        self.assertFalse(windows.belongs_to_run(
            9000,9040,parent_for=ppid_from(chain)))

    def test_linux_parent_read_uses_real_procfs_without_private_output(self):
        self.assertEqual(windows._parent_linux(os.getpid()),os.getppid())
        with self.assertRaises(ValueError):
            windows._parent_linux(True)

    def test_stage316_private_host_verifier_calls_process_bound_locator(self):
        src=(Path(__file__).resolve().parents[1]/
             "tools/nexium_private_original_gfx_optical_316.py").read_text()
        self.assertIn("host=private_xlib.capture_process_window(proc.pid)",src)
        self.assertNotIn("wid=optical._window()",src)
        self.assertIn("optical.verify_optical_image(host,index,reference)",src)


if __name__=="__main__":
    unittest.main()

"""Stage321: ROM-free Xlib binding tests. Never access original game assets."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools import nexium_private_xlib_capture_321 as stage

XLIB_AVAILABLE=importlib.util.find_spec("Xlib") is not None
PIL_AVAILABLE=importlib.util.find_spec("PIL") is not None


class FakeImage:
    @staticmethod
    def frombytes(mode, size, raw, format_, layout):
        return (mode,size,raw,format_,layout)


class FakeWindow:
    def __init__(self, id_, *, name="", pid=None, width=440, height=280,
                 visible=True, children=()):
        self.id=id_
        self.name=name
        self.pid=pid
        self.width=width
        self.height=height
        self.visible=visible
        self.children=children
    def get_wm_name(self):
        return self.name
    def get_attributes(self):
        return SimpleNamespace(map_state=2 if self.visible else 0)
    def query_tree(self):
        return SimpleNamespace(children=self.children)
    def get_full_property(self, atom, value_type):
        if self.pid is None:
            return None
        return SimpleNamespace(format=32,value=[self.pid])
    def get_geometry(self):
        return SimpleNamespace(width=self.width,height=self.height,depth=24)
    def get_image(self,x,y,w,h,fmt,mask):
        return SimpleNamespace(depth=24,data=b"\x10\x20\x30\x00"*(w*h))


class FakeServer:
    def __init__(self, root):
        self.root=root
        self.closed=False
    def screen(self):
        return SimpleNamespace(root=self.root)
    def intern_atom(self,name,only_if_exists=False):
        return 27
    def close(self):
        self.closed=True


@unittest.skipUnless(XLIB_AVAILABLE,"python-xlib is optional in Python baseline CI")
class Stage321XlibPureROMFreeTests(unittest.TestCase):
    def tree(self,*children):
        return FakeServer(FakeWindow(100,children=children))

    def test_one_visible_window_owned_by_exact_launched_pid(self):
        server=self.tree(FakeWindow(200,name="NeXium Diagnostic",pid=6500))
        self.assertEqual([w.id for w in stage._find_windows(
            server,6500,parent_for=lambda x:1)],[200])

    def test_descendant_window_belongs_to_launched_emulator(self):
        server=self.tree(FakeWindow(200,name="NeXium",pid=6600))
        self.assertEqual([w.id for w in stage._find_windows(
            server,6500,parent_for=lambda x:{6600:6500}[x])],[200])

    def test_old_unrelated_emulator_window_is_not_evidence(self):
        server=self.tree(FakeWindow(200,name="NeXium",pid=3200))
        self.assertEqual(stage._find_windows(
            server,6500,parent_for=lambda x:1),[])

    def test_missing_or_hidden_pid_never_matches(self):
        for pid,visible in ((None,True),(6500,False)):
            with self.subTest(pid=pid,visible=visible):
                server=self.tree(FakeWindow(200,name="NeXium",
                                             pid=pid,visible=visible))
                self.assertEqual(stage._find_windows(
                    server,6500,parent_for=lambda x:1),[])

    def test_ambiguous_same_run_windows_are_refused(self):
        server=self.tree(
            FakeWindow(200,name="NeXium",pid=6500),
            FakeWindow(201,name="NeXium",pid=6500))
        self.assertEqual(stage._find_windows(
            server,6500,parent_for=lambda x:1),[])

    def test_too_many_unrelated_windows_fails_closed(self):
        server=self.tree(*(FakeWindow(200+i) for i in range(stage.MAX_WINDOWS+3)))
        self.assertEqual(stage._find_windows(
            server,6500,parent_for=lambda x:1),[])

    def test_x11_raw_image_is_read_from_xserver_not_source_pil(self):
        win=FakeWindow(200,name="NeXium",pid=6500)
        result=stage._capture(win,FakeImage)
        self.assertEqual(result[:2],("RGB",(440,280)))
        self.assertEqual(result[-1],"BGRX")
        self.assertEqual(len(result[2]),440*280*4)

    def test_invalid_window_depth_geometry_and_image_length_refused(self):
        win=FakeWindow(200,name="NeXium",pid=6500,width=42)
        with self.assertRaises(ValueError):
            stage._capture(win,FakeImage)
        win.width=440
        win.get_geometry=lambda:SimpleNamespace(width=440,height=280,depth=16)
        with self.assertRaises(ValueError):
            stage._capture(win,FakeImage)

    def test_capture_closes_xlib_socket_even_without_owner(self):
        server=self.tree(FakeWindow(200,name="NeXium",pid=8000))
        self.assertIsNone(stage.capture_process_window(
            6500,display_factory=lambda:server,
            parent_for=lambda x:1,image_module=FakeImage))
        self.assertTrue(server.closed)

    def test_exact_owner_frame_is_captured_without_files(self):
        server=self.tree(FakeWindow(200,name="NeXium",pid=6500))
        result=stage.capture_process_window(
            6500,display_factory=lambda:server,
            parent_for=lambda x:1,image_module=FakeImage)
        self.assertEqual(result[1],(440,280))
        self.assertTrue(server.closed)

    def test_invalid_process_id_never_opens_xserver(self):
        calls=[]
        self.assertIsNone(stage.capture_process_window(
            True,display_factory=lambda:calls.append(1)))
        self.assertEqual(calls,[])


@unittest.skipUnless(XLIB_AVAILABLE and PIL_AVAILABLE and
    bool(os.environ.get("DINO_STAGE321_LIVE_X11")) and bool(os.environ.get("DISPLAY")),
    "real invented-window X11 smoke only runs in dedicated Xvfb job")
class Stage321RealX11WindowOnlyTests(unittest.TestCase):
    def test_live_xserver_getimage_bound_to_our_child_process(self):
        # This child draws an INVENTED solid color; never touches a ROM
        # or claims a real NeXium emulator or Switch guest existed.
        child_code=r"""
import os, tkinter as tk
from Xlib import display, Xatom
t=tk.Tk()
t.title('NeXium Stage321 Invented Window (NOT EMULATOR)')
t.geometry('440x280+0+0')
tk.Label(t,bg='#437ac5',borderwidth=0).pack(fill='both',expand=True)
t.update()
d=display.Display()
outer=d.create_resource_object('window',t.winfo_id()).query_tree().parent
outer.change_property(d.intern_atom('_NET_WM_PID'),Xatom.CARDINAL,32,[os.getpid()])
d.sync()
print('READY',flush=True)
t.mainloop()
"""
        child=subprocess.Popen([sys.executable,"-c",child_code],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),"READY")
            img=None
            for _ in range(50):
                img=stage.capture_process_window(child.pid)
                if img is not None:
                    break
                if child.poll() is not None:
                    break
                time.sleep(.1)
            self.assertIsNotNone(img)
            self.assertEqual(img.size,(440,280))
            observed=img.getpixel((220,140))
            self.assertTrue(all(abs(x-y)<7 for x,y in
                                zip(observed,(67,122,197))))
            self.assertIsNone(stage.capture_process_window(child.pid+10000))
        finally:
            child.terminate()
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)


class Stage321SourceIntegrationTests(unittest.TestCase):
    def test_original_graphics_verifier_uses_xlib_not_imagemagick(self):
        source=(Path(__file__).resolve().parents[1]/
                "tools/nexium_private_original_gfx_optical_316.py").read_text()
        self.assertIn("host=private_xlib.capture_process_window(proc.pid)",source)
        self.assertNotIn('optical._capture(wid,root/"host-window.png")',source)
        self.assertNotIn("wid=x11.window_for_process(proc.pid)",source)


if __name__=="__main__":
    unittest.main()

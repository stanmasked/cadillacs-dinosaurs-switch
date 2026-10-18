#!/usr/bin/env python3
"""Play or inspect the ROM-free training room on a desktop.

This compiles and executes the exact C arena + procedural SFX engines
used by the Switch NRO. It does NOT emulate Switch hardware, GPU, IPC or
audout. The 384x224 rendering is an independent geometric host preview,
not Switch framebuffer evidence or original Cadillacs and Dinosaurs art.

Headless: python3 tools/dino_host_preview.py --headless --ticks 180
Interactive: python3 tools/dino_host_preview.py
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
WIDTH,HEIGHT=384,224
PIXELS=WIDTH*HEIGHT*3
LEFT,RIGHT,UP,DOWN,ATTACK,JUMP,SPAR=(1,2,4,8,16,32,64)


class Status(ctypes.Structure):
    _fields_=[
        ('x',ctypes.c_int32),('y',ctypes.c_int32),
        ('z',ctypes.c_int32),('dummy_x',ctypes.c_int32),
        ('dummy_y',ctypes.c_int32),
        ('ticks',ctypes.c_uint32),('events',ctypes.c_uint32),
        ('successful_hits',ctypes.c_uint32),
        ('player_pose',ctypes.c_uint32),('enemy_pose',ctypes.c_uint32),
        ('combo',ctypes.c_uint32),('player_hp',ctypes.c_uint32),
        ('enemy_hp',ctypes.c_uint32),('sparring',ctypes.c_uint32),
        ('pcm_digest',ctypes.c_uint64),
        ('gameplay_digest',ctypes.c_uint64),
    ]


class HostArena:
    def __init__(self):
        compiler=shutil.which('gcc')
        if not compiler:
            raise RuntimeError('Host GCC unavailable; no emulator was run')
        self.temp=tempfile.TemporaryDirectory(prefix='dino-native-host-')
        self.path=Path(self.temp.name)/'dinohost.so'
        sources=['source/dino_arena.c','source/dino_sfx.c',
                 'source/dino_replay.c','source/dino_replay_witness.c',
                 'source/dino_pcm_witness.c',
                 'tools/dino_host_bridge.c']
        cmd=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-fPIC','-shared','-Isource',
             *(str(ROOT/x) for x in sources),'-o',str(self.path)]
        result=subprocess.run(cmd,capture_output=True,text=True,check=False)
        if result.returncode:
            self.temp.cleanup()
            raise RuntimeError('Portable C compilation failed')
        self.dll=ctypes.CDLL(str(self.path))
        self.dll.dino_host_reset.argtypes=[]
        self.dll.dino_host_step.argtypes=[ctypes.c_uint32,ctypes.c_uint32]
        self.dll.dino_host_demo_step.argtypes=[ctypes.c_uint32]
        self.dll.dino_host_status.argtypes=[ctypes.POINTER(Status)]
        self.dll.dino_host_render.argtypes=[
            ctypes.POINTER(ctypes.c_uint8),ctypes.c_size_t]
        self.buffer=(ctypes.c_uint8*PIXELS)()
        self.reset()

    def close(self):
        self.temp.cleanup()

    def reset(self):
        self.dll.dino_host_reset()

    def step(self,held=0,pressed=0):
        self.dll.dino_host_step(held,pressed)

    def demo_step(self,tick):
        # The replay decisions come directly from the same portable C
        # routine compiled into the Switch NRO. No duplicate Python script.
        self.dll.dino_host_demo_step(tick)

    def status(self):
        item=Status()
        self.dll.dino_host_status(ctypes.byref(item))
        return item

    def render_rgb(self):
        self.dll.dino_host_render(self.buffer,PIXELS)
        return bytes(self.buffer)

    def ppm(self):
        return f'P6\n{WIDTH} {HEIGHT}\n255\n'.encode()+self.render_rgb()


def headless(ticks=180,out_frame=None):
    if not isinstance(ticks,int) or not 1<=ticks<=3600:
        raise ValueError('ticks must be within 1..3600')
    engine=HostArena()
    try:
        for t in range(ticks):
            engine.demo_step(t)
        state=engine.status()
        frame=engine.render_rgb()
        if out_frame is not None:
            # Never clobber a prior capture or follow an existing symlink.
            with Path(out_frame).open('xb') as f:
                f.write(f'P6\n{WIDTH} {HEIGHT}\n255\n'.encode())
                f.write(frame)
        return {
            'schema':'dino-native-host-smoke-v1',
            'runtime':'native_host_not_switch_emulator',
            'ticks':state.ticks,
            'player_x':state.x,'player_y':state.y,
            'player_hp':state.player_hp,'enemy_hp':state.enemy_hp,
            'successful_hits':state.successful_hits,
            'combo':state.combo,'sparring':bool(state.sparring),
            'frame_rgb_sha256':hashlib.sha256(frame).hexdigest(),
            'pcm_fnv64':f'{state.pcm_digest:016x}',
            'gameplay_witness_fnv64':f'{state.gameplay_digest:016x}',
            'switch_gpu_verified':False,
            'switch_audio_verified':False,
            'switch_emulator_verified':False,
        }
    finally:
        engine.close()


class FixedTickScheduler:
    """Deterministic 60 Hz host UI timing, independent of Tk repaint rate.

    Two protections matter: stalled desktops do not explode into unlimited
    catch-up work, and a key edge remains pending until a simulation tick.
    Every game step still executes the unchanged C engine.
    """
    NS_PER_SECOND=1_000_000_000
    MAX_CATCHUP_STEPS=8
    MAX_ELAPSED_NS=250_000_000

    def __init__(self):
        self.carry=0
        self.dropped_ticks=0

    def advance(self,elapsed_ns):
        elapsed=max(0,min(int(elapsed_ns),self.MAX_ELAPSED_NS))
        total=self.carry+elapsed*60
        due,remainder=divmod(total,self.NS_PER_SECOND)
        if due>self.MAX_CATCHUP_STEPS:
            self.dropped_ticks+=due-self.MAX_CATCHUP_STEPS
            self.carry=0
            return self.MAX_CATCHUP_STEPS
        self.carry=remainder
        return due


class KeyboardInput:
    """Single key-edge translator for desktop play and GUI smoke tests.

    Tk itself owns key repeat and focus; actions only fire on a new
    key-down edge, while held directions apply to every 60Hz tick.
    """
    DIRECTIONS={
        'left':LEFT,'a':LEFT,'right':RIGHT,'d':RIGHT,
        'up':UP,'w':UP,'down':DOWN,'s':DOWN,
    }
    ACTIONS={'j':ATTACK,'k':JUMP,'l':SPAR}

    def __init__(self):
        self.held=set()
        self.pending=0
        self.reset_requested=False
        self.exit_requested=False

    def key_down(self,key):
        key=key.lower()
        if key=='escape':
            self.exit_requested=True
        elif key=='r':
            if key not in self.held:
                self.reset_requested=True
        elif key not in self.held and key in self.ACTIONS:
            self.pending|=self.ACTIONS[key]
        self.held.add(key)

    def key_up(self,key):
        self.held.discard(key.lower())

    def tick_input(self):
        directions=0
        for key in self.held:
            directions|=self.DIRECTIONS.get(key,0)
        actions=self.pending
        self.pending=0
        return directions,actions


def gui_smoke():
    """Run real Tk PhotoImage/Canvas and *synthetic* keyboard events.

    Linux Xvfb allows testing the desktop GUI without a physical display.
    This is an honest desktop-frontend test, not Switch emulation or
    evidence of a rendered frame from an NRO.
    """
    import tkinter as tk
    root=tk.Tk()
    root.title('Native ROM-free GUI smoke — not Switch emulation')
    game=None
    try:
        game=HostArena()
        inputs=KeyboardInput()
        canvas=tk.Canvas(root,width=WIDTH*2,height=HEIGHT*2,
                         highlightthickness=0)
        canvas.pack()
        root.bind('<KeyPress>',lambda e:inputs.key_down(e.keysym))
        root.bind('<KeyRelease>',lambda e:inputs.key_up(e.keysym))
        root.update()
        root.focus_force()
        root.update()

        def send(kind,keysym):
            root.event_generate(kind,keysym=keysym)
            root.update()

        for frame in range(9):
            if frame==0: send('<KeyPress>','Right')
            if frame==4: send('<KeyRelease>','Right')
            if frame==5: send('<KeyPress>','j')
            if frame==6: send('<KeyRelease>','j')
            game.step(*inputs.tick_input())

        status=game.status()
        if (status.x,status.y,status.ticks)!=(98,151,9):
            raise RuntimeError('Native GUI controller did not move correctly')
        if status.successful_hits!=0 or not (status.events==0):
            raise RuntimeError('Native GUI attack sequence mismatch')

        ppm=game.ppm()
        photo=tk.PhotoImage(data=ppm,format='PPM').zoom(2,2)
        image=canvas.create_image(0,0,anchor='nw',image=photo)
        root.update()
        if (photo.width(),photo.height())!=(WIDTH*2,HEIGHT*2):
            raise RuntimeError('Native GUI pixel dimensions mismatch')
        if tuple(photo.get(98*2,126*2))!=(62,180,208):
            raise RuntimeError('Native GUI player pixel mismatch')
        if tuple(photo.get(250*2,127*2))!=(190,126,74):
            raise RuntimeError('Native GUI dummy pixel mismatch')
        if not canvas.find_withtag(image):
            raise RuntimeError('Native GUI canvas image was not presented')

        return {
            'schema':'dino-native-gui-smoke-v1',
            'runtime':'tk_desktop_not_switch_emulator',
            'ticks':status.ticks,'player_x':status.x,
            'held_input_verified':True,
            'edge_input_verified':True,
            'tk_image_rendered':True,
            'image_dimensions':[photo.width(),photo.height()],
            'rgb_sha256':hashlib.sha256(game.render_rgb()).hexdigest(),
            'switch_emulator_verified':False,
            'switch_gpu_verified':False,
            'switch_audio_verified':False,
        }
    finally:
        if game is not None:
            game.close()
        root.destroy()


def interactive():
    # No GUI dependency is imported for synthetic headless CI mode.
    import tkinter as tk
    root=tk.Tk()
    root.title('ROM-free C training arena — native host, NOT Switch emulation')
    game=HostArena()
    canvas=tk.Canvas(root,width=WIDTH*2,height=HEIGHT*2,
                     highlightthickness=0)
    canvas.pack()
    status_line=tk.StringVar()
    tk.Label(root,textvariable=status_line,font=('monospace',10)).pack()
    tk.Label(root,text='Arrows/WASD: move  J: attack  K: jump  L: spar  R: reset  Esc: exit').pack()
    inputs=KeyboardInput()
    scheduler=FixedTickScheduler()
    last_ns=time.monotonic_ns()
    holder={'photo':None,'image':None}

    def tick():
        nonlocal last_ns
        if inputs.exit_requested:
            root.destroy()
            return
        now=time.monotonic_ns()
        due=scheduler.advance(now-last_ns)
        last_ns=now
        if inputs.reset_requested:
            game.reset()
            inputs.reset_requested=False
            scheduler.carry=0
        for _ in range(due):
            game.step(*inputs.tick_input())
        p=game.ppm()
        holder['photo']=tk.PhotoImage(data=p,format='PPM').zoom(2,2)
        if holder['image'] is None:
            holder['image']=canvas.create_image(0,0,anchor='nw',
                                                image=holder['photo'])
        else:
            canvas.itemconfigure(holder['image'],image=holder['photo'])
        s=game.status()
        status_line.set(
            f'Tick {s.ticks}  HP {s.player_hp}/5  Enemy {s.enemy_hp}/3'
            f'  Hits {s.successful_hits}  Combo {s.combo}/3'
            f'  Spar {"ON" if s.sparring else "OFF"}')
        root.after(16,tick)

    def close():
        game.close()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    root.bind('<KeyPress>',lambda e:inputs.key_down(e.keysym))
    root.bind('<KeyRelease>',lambda e:inputs.key_up(e.keysym))
    root.update_idletasks()
    root.focus_force()
    root.after(8,tick)
    try:
        root.mainloop()
    finally:
        game.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--gui-smoke',action='store_true',
                        help='Run actual Tk desktop pixels/keys smoke; requires Xvfb or display')
    parser.add_argument('--ticks',type=int,default=180)
    parser.add_argument('--out-frame',type=Path,
                        help='Optional PPM frame path; never overwrite')
    args=parser.parse_args(argv)
    if args.headless and args.gui_smoke:
        parser.error('choose either --headless or --gui-smoke')
    if args.gui_smoke:
        if args.out_frame:
            parser.error('--out-frame requires --headless')
        try:
            report=gui_smoke()
        except (RuntimeError,OSError):
            print(json.dumps({'status':'HOST_GUI_SMOKE_FAILED',
                              'switch_emulator_verified':False}))
            return 2
        print(json.dumps(report,sort_keys=True))
        return 0
    if not args.headless:
        if args.out_frame:
            parser.error('--out-frame requires --headless')
        interactive()
        return 0
    try:
        report=headless(args.ticks,args.out_frame)
    except (OSError,RuntimeError,ValueError):
        print(json.dumps({'status':'HOST_SMOKE_FAILED'},sort_keys=True))
        return 2
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())

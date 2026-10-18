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
    ]


class HostArena:
    def __init__(self):
        compiler=shutil.which('gcc')
        if not compiler:
            raise RuntimeError('Host GCC unavailable; no emulator was run')
        self.temp=tempfile.TemporaryDirectory(prefix='dino-native-host-')
        self.path=Path(self.temp.name)/'dinohost.so'
        sources=['source/dino_arena.c','source/dino_sfx.c',
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

    def status(self):
        item=Status()
        self.dll.dino_host_status(ctypes.byref(item))
        return item

    def render_rgb(self):
        self.dll.dino_host_render(self.buffer,PIXELS)
        return bytes(self.buffer)

    def ppm(self):
        return f'P6\n{WIDTH} {HEIGHT}\n255\n'.encode()+self.render_rgb()


def demo_input(t):
    """Designed 180-frame scenario of locomotion, combo, sparring and jump."""
    held=RIGHT if t<70 else 0
    pressed=(ATTACK if t in (75,90,105,148) else 0)
    if t==130:
        pressed|=SPAR
    if t==155:
        pressed|=JUMP
    return held,pressed


def headless(ticks=180,out_frame=None):
    if not isinstance(ticks,int) or not 1<=ticks<=3600:
        raise ValueError('ticks must be within 1..3600')
    engine=HostArena()
    try:
        for t in range(ticks):
            engine.step(*demo_input(t))
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
            'switch_gpu_verified':False,
            'switch_audio_verified':False,
            'switch_emulator_verified':False,
        }
    finally:
        engine.close()


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
    held_keys=set()
    pending=0
    holder={'photo':None,'image':None}
    directions={
        'left':LEFT,'a':LEFT,'right':RIGHT,'d':RIGHT,
        'up':UP,'w':UP,'down':DOWN,'s':DOWN,
    }
    actions={'j':ATTACK,'k':JUMP,'l':SPAR}

    def key_down(event):
        nonlocal pending
        key=event.keysym.lower()
        if key=='escape':
            root.destroy()
            return
        if key=='r':
            game.reset()
            return
        if key not in held_keys and key in actions:
            pending|=actions[key]
        held_keys.add(key)

    def key_up(event):
        held_keys.discard(event.keysym.lower())

    def tick():
        nonlocal pending
        keys=0
        for key in held_keys:
            keys|=directions.get(key,0)
        game.step(keys,pending)
        pending=0
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
    root.bind('<KeyPress>',key_down)
    root.bind('<KeyRelease>',key_up)
    root.after(16,tick)
    try:
        root.mainloop()
    finally:
        game.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--ticks',type=int,default=180)
    parser.add_argument('--out-frame',type=Path,
                        help='Optional PPM frame path; never overwrite')
    args=parser.parse_args(argv)
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

#!/usr/bin/env python3
"""Local-only MAME dino readiness, ROM verification and render-capture runner.

Requires a locally installed instrumented MAME executable, the user's own
dino.zip and separate qsound_hle.zip. Never downloads, uploads or bundles
game assets. Exit 0 means a complete *format-valid* dump, NOT gameplay parity.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

try:
    from tools.mame_rom_readiness import audit_game, check_device
    from tools.mame_playback_plan import playback_plan, confirm_playback_unchanged
    from tools.mame_capture_motion_audit import audit_sequence
except ModuleNotFoundError:
    from mame_rom_readiness import audit_game, check_device
    from mame_playback_plan import playback_plan, confirm_playback_unchanged
    from mame_capture_motion_audit import audit_sequence

STREAMS = {
    'gfxram-be.bin': 196608, 'cps-a-be.bin': 64,
    'cps-b-be.bin': 64, 'buffered-obj-be.bin': 2048,
    'palette-rgb24.bin': 9216, 'reference-rgb24.bin': 258048,
}


def safe_child(root, frame, suffix):
    return root / f'frame-{frame:08d}.{suffix}'


def validate_dump(root, frame):
    """Validate a complete single-pass dump, without returning RAM bytes."""
    stem=f'frame-{frame:08d}'
    meta=json.loads(safe_child(root,frame,'manifest.json').read_text('utf-8'))
    required={
        'game':'dino', 'frame':frame,
        'capture_hook':'screen_update_cps1_complete',
        'full_cliprect':True, 'buffered_obj_same_render_pass':True,
        'reference_pixel_encoding':'rgb24_palette_resolved',
        'palette_source':'MAME_effective_pen_color',
        'raw_word_endianness':'big',
        'reference_width':384, 'reference_height':224,
        'pixel_parity_verified':False,
    }
    for field,expected in required.items():
        if type(meta.get(field)) is not type(expected) or meta[field]!=expected:
            raise ValueError(f'{stem}: invalid manifest field {field}')
    files={}
    for suffix,length in STREAMS.items():
        data=safe_child(root,frame,suffix).read_bytes()
        if len(data)!=length:
            raise ValueError(f'{stem}.{suffix}: {len(data)} bytes, expected {length}')
        size_field={'gfxram-be.bin':'gfxram_bytes',
                    'cps-a-be.bin':'cps_a_bytes',
                    'cps-b-be.bin':'cps_b_bytes',
                    'buffered-obj-be.bin':'buffered_obj_bytes',
                    'palette-rgb24.bin':'palette_bytes',
                    'reference-rgb24.bin':'reference_rgb_bytes'}[suffix]
        if type(meta.get(size_field)) is not int or meta[size_field]!=length:
            raise ValueError(f'{stem}: invalid manifest length {size_field}')
        files[suffix]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return {'frame':frame,'name':stem,'streams':files,
            'buffered_obj_present':True,'same_pass_claimed_by_hook':True}


def executable_path(executable):
    value=os.fspath(executable)
    if os.path.sep in value or (os.path.altsep and os.path.altsep in value):
        p=Path(value).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f'MAME executable not found: {p}')
        return str(p.resolve())
    found=shutil.which(value)
    if found is None:
        raise FileNotFoundError(f'MAME executable is not in PATH: {value}')
    return found


def run_command(argv,*,env=None,seconds=300):
    try:
        result=subprocess.run(argv,env=env,check=False,timeout=seconds,
                              capture_output=True,text=True,errors='replace')
    except subprocess.TimeoutExpired:
        raise ValueError(f'MAME subprocess exceeded wall-time limit ({seconds}s)') from None
    return {'exit_code':result.returncode,
            'stdout_tail':result.stdout[-2400:],
            'stderr_tail':result.stderr[-2400:]}


def run_capture(*,mame,rom_dir,output_dir,start,count,seconds,wall_timeout=300,
                require_device=True,probe_only=False,playback_inp=None):
    """Run ROM preflight and optional instrumented MAME without shell execution."""
    if any(type(v) is not int for v in (start,count,seconds,wall_timeout)):
        raise ValueError('Frame numbers and timeouts must be integers')
    if not 0<=start<=99999999 or not 1<=count<=120 or start+count>100000000:
        raise ValueError('Invalid capture frame range')
    if not 1<=seconds<=600 or not 1<=wall_timeout<=3600:
        raise ValueError('Requested run/timeout outside bounds')
    rom_dir=Path(rom_dir).expanduser().resolve()
    output_dir=Path(output_dir).expanduser().resolve()
    game=rom_dir/'dino.zip'
    if not game.is_file():
        raise FileNotFoundError(f'Missing private game archive: {game}')
    preflight=audit_game(game)
    device=check_device(rom_dir/'qsound_hle.zip')
    result={
        'format':'cps1_mame_local_run_v1','game':'dino',
        'expected_first_frame':start,'requested_frame_count':count,
        'capture_source':'user_local_instrumented_mame',
        'core_rom_metadata_valid':preflight['core_complete'],
        'archival_plds_all_known':preflight['all_archival_plds_known'],
        'qsound_device_valid':device['valid'],
        'qsound_device_status':device['status'],
        'external_binary_provenance_unverified':True,
        'gameplay_reconstructed':False,'pixel_parity_verified':False,
        'native_switch_runtime_tested':False,
        'capture_format_valid':False,
        'captured_frames':[],
    }
    if not preflight['core_complete']:
        raise ValueError('Original core dino ROM bytes failed known CRC/length checks')
    if require_device and not device['valid']:
        raise ValueError('Missing or invalid qsound_hle.zip; obtain/verify privately')
    playback_args, playback_meta=playback_plan(playback_inp)
    result['input_replay']=playback_meta
    executable=executable_path(mame)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f'Capture directory is nonempty: {output_dir}')
    result['mame_version_check']=run_command([executable,'-version'],
                                            seconds=min(60,wall_timeout))
    if result['mame_version_check']['exit_code']!=0:
        raise ValueError('MAME -version did not complete successfully')
    verify_cmd=[executable,'dino','-rompath',str(rom_dir),'-verifyroms']
    result['romset_verification']=run_command(verify_cmd,seconds=wall_timeout)
    if result['romset_verification']['exit_code']!=0:
        raise ValueError('MAME -verifyroms dino failed; inspect MAME version and device set')
    if probe_only:
        result['status']='verified_roms_only_no_game_launched'
        return result
    output_dir.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    env.update(CPS1_RENDER_DUMP_DIR=str(output_dir),
               CPS1_RENDER_DUMP_START=str(start),
               CPS1_RENDER_DUMP_COUNT=str(count))
    run=[executable,'dino','-rompath',str(rom_dir),'-skip_gameinfo',
         '-nothrottle','-seconds_to_run',str(seconds)]+playback_args
    # A replay must not silently continue into attract mode after its input
    # stream ends, or those later frames could masquerade as first-level data.
    if playback_args:
        run.append('-exit_after_playback')
    result['emulator_process']=run_command(run,env=env,seconds=wall_timeout)
    if not confirm_playback_unchanged(playback_inp,playback_meta):
        raise ValueError('MAME input playback bytes changed during execution')
    if result['emulator_process']['exit_code']!=0:
        raise ValueError('Instrumented MAME process did not complete successfully')
    result['captured_frames']=[validate_dump(output_dir,start+i) for i in range(count)]
    # A complete dump may still be an attract-mode or static screen.
    # Motion evidence is diagnostic only; never infer a playable first level.
    result['sequence_motion_diagnostic']=audit_sequence(output_dir,start,count)
    result['first_level_verified']=False
    result['capture_format_valid']=True
    result['status']='complete_capture_format_verified_not_gameplay_parity'
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mame',default='mame',help='Local *instrumented* MAME executable')
    parser.add_argument('--rom-dir',type=Path,required=True,
                        help='Private directory containing dino.zip and qsound_hle.zip')
    parser.add_argument('--capture-dir',type=Path,required=True)
    parser.add_argument('--start',type=int,default=900)
    parser.add_argument('--count',type=int,default=6)
    parser.add_argument('--seconds-to-run',type=int,default=30)
    parser.add_argument('--wall-timeout',type=int,default=300)
    parser.add_argument('--playback-inp',type=Path,
                        help='User-local recorded MAME .inp for reproducible stage entry')
    parser.add_argument('--probe-only',action='store_true',
                        help='Run -version and -verifyroms, but not the game')
    parser.add_argument('--allow-unverified-device',action='store_true',
                        help='Let MAME -verifyroms decide if the separate device set is needed')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.report.exists():
            raise FileExistsError('Report exists; refusing to overwrite')
        data=run_capture(
            mame=args.mame,rom_dir=args.rom_dir,output_dir=args.capture_dir,
            start=args.start,count=args.count,seconds=args.seconds_to_run,
            wall_timeout=args.wall_timeout,probe_only=args.probe_only,
            require_device=not args.allow_unverified_device,
            playback_inp=args.playback_inp)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        with args.report.open('x',encoding='utf-8') as stream:
            json.dump(data,stream,indent=2)
            stream.write('\n')
        print(data['status'])
        print('Actual first-level gameplay and pixel parity are NOT verified.')
        return 0
    except (ValueError,OSError,TypeError,RuntimeError,json.JSONDecodeError) as exc:
        print('MAME local capture refused:',exc,file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())

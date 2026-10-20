#!/usr/bin/env python3
"""Optional ROM-free NeXium X11 counter-frame observation (Stage 250).

Observe four host-window pixels in one XGetImage after real host T/ZR,
independently of the NRO's submitted framebuffer CSV. This is sampled
X11 evidence, NOT photons, input latency, original graphics or guest
HID proof. Never store raw images, input paths or window identities.
The pixel map is for the pinned 1280x720 NeXium UI; fail closed if changed.
"""
import ctypes
import ctypes.util
import json
import threading
import time

WINDOW_SIZE=(1280,720)
POINTS={
    'caption':(795,646), 'impact':(471,323),
    'player':(345,410), 'ground':(120,617),
}
EXPECTED={
    'caption':(91,235,201), 'impact':(255,243,164),
    'player':(62,180,208), 'ground':(62,83,74),
}
STATUS='HOST_WINDOW_COUNTER_PIXELS_OBSERVED_UNBOUND'
INCONCLUSIVE='INCONCLUSIVE_NO_HOST_WINDOW_COUNTER_FRAME'
MIN_X=min(x for x,_ in POINTS.values())
MIN_Y=min(y for _,y in POINTS.values())
MAX_X=max(x for x,_ in POINTS.values())
MAX_Y=max(y for _,y in POINTS.values())
# Calibrated Stage 250 host-window mapping; these are X11 pixels,
# NOT Nintendo native-buffer coordinates. Sample mid-cell interiors.
TOKEN_START=(918,665)
TOKEN_END=(1150,665)
TOKEN_BITS=tuple((round(23.33333333+0.96354167*(946+12*bit)),665)
                 for bit in range(16))
TOKEN_ONE=(250,250,250)
TOKEN_ZERO=(15,35,50)
TOKEN_SYNC_START=(255,0,153)
TOKEN_SYNC_END=(0,255,204)
MIN_X=min(MIN_X,TOKEN_START[0],TOKEN_END[0],*(x for x,_ in TOKEN_BITS))
MAX_X=max(MAX_X,TOKEN_START[0],TOKEN_END[0],*(x for x,_ in TOKEN_BITS))
MAX_Y=max(MAX_Y,TOKEN_START[1])


def decode_frame_token(colors):
    """Accept exact two synchronizers and sixteen binary cells in ONE image."""
    if len(colors)!=18 or colors[0]!=TOKEN_SYNC_START or colors[-1]!=TOKEN_SYNC_END:
        return None
    token=0
    for bit,color in enumerate(colors[1:-1]):
        if color==TOKEN_ONE:
            token|=1<<bit
        elif color!=TOKEN_ZERO:
            return None
    return token



def classify(pre, samples):
    """Require pre-ZR blank caption/impact and all four in ONE later image."""
    if pre is None or tuple(pre.get('ground',()))!=EXPECTED['ground']:
        return INCONCLUSIVE
    if (tuple(pre.get('caption',()))==EXPECTED['caption'] or
            tuple(pre.get('impact',()))==EXPECTED['impact']):
        return INCONCLUSIVE
    if any(all(tuple(s.get(k,()))==rgb for k,rgb in EXPECTED.items())
           for s in samples):
        return STATUS
    return INCONCLUSIVE


def result(status, samples=0, baseline=False, reason=''):
    return {
        'schema':'dino-nexium-host-counter-frame-v1',
        'status':status,
        'host_x11_window_counter_pixels_observed':status==STATUS,
        'counter_transition_baseline_observed':bool(baseline),
        'same_x11_image_four_pixel_match':status==STATUS,
        'frames_sampled':min(max(int(samples),0),200),
        'diagnostic_code':reason,
        'native_guest_counter_event_bound':False,
        'host_window_pixel_latency_verified':False,
        'physical_display_verified':False,
        'physical_controller_verified':False,
        'original_arcade_graphics_verified':False,
    }

def empty_capture_interval_result():
    # Explicitly inconclusive even if T keydown failed or no guest marker.
    return {
        'schema':'dino-nexium-host-x11-sample-window-v1',
        'status':'INCONCLUSIVE_NO_BOUND_X11_CAPTURE_WINDOW',
        'host_x11_capture_window_observed':False,
        'frame_token_u16':None,
        'post_keydown_command_to_capture_begin_us':None,
        'post_keydown_command_to_capture_end_us':None,
        'xgetimage_call_duration_upper_us':None,
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'precise_input_to_display_latency_verified':False,
        'actual_guest_input_delivery_timestamp_verified':False,
        'physical_controller_verified':False,
        'physical_display_verified':False,
        'gpu_scanout_timestamp_verified':False,
    }

def empty_command_bracket_result():
    return {
        'schema':'dino-nexium-host-keydown-call-capture-v1',
        'status':'INCONCLUSIVE_NO_HOST_KEYDOWN_BRACKET',
        'host_command_to_x11_bracket_observed':False,
        'host_frame_token_u16':None,
        'keydown_command_duration_floor_us':None,
        'keydown_command_duration_ceil_us':None,
        'keydown_call_begin_to_x11_begin_us':None,
        'keydown_call_begin_to_x11_end_us':None,
        'keydown_call_complete_to_x11_begin_us':None,
        'keydown_call_complete_to_x11_end_us':None,
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'guest_input_delivery_timestamp_verified':False,
        'first_visible_frame_onset_verified':False,
        'physical_joycon_latency_verified':False,
        'physical_switch_lcd_latency_verified':False,
        'gpu_scanout_timestamp_verified':False,
        'cross_mode_causal_comparison_verified':False,
    }

def empty_transition_bracket_result():
    return {
        'schema':'dino-nexium-host-x11-transition-bracket-v1',
        'status':'INCONCLUSIVE_NO_POST_TRIGGER_ABSENT_SAMPLE',
        'post_trigger_absent_x11_images':0,
        'host_x11_transition_sample_bracket_observed':False,
        'x11_positive_frame_token_u16':None,
        'last_negative_x11_pixel_rgb':None,
        'last_negative_xgetimage_begin_offset_us':None,
        'last_negative_xgetimage_end_offset_us':None,
        'first_positive_xgetimage_begin_offset_us':None,
        'first_positive_xgetimage_end_offset_us':None,
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'first_visible_frame_onset_verified':False,
        'precise_input_to_display_latency_verified':False,
        'guest_input_delivery_timestamp_verified':False,
        'physical_controller_verified':False,
        'physical_display_verified':False,
        'gpu_scanout_timestamp_verified':False,
        'cross_mode_causal_comparison_verified':False,
    }

def empty_sample_sequence_result():
    return {
        'schema':'dino-nexium-host-x11-sample-sequence-v1',
        'status':'INCONCLUSIVE_NO_ORDERED_X11_SAMPLE_SEQUENCE',
        'ordered_host_x11_samples_observed':False,
        'post_command_negative_samples':0,
        'matching_positive_frame_token_u16':None,
        'samples':[],
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'precise_first_visible_frame_onset_verified':False,
        'guest_input_delivery_timestamp_verified':False,
        'physical_controller_verified':False,
        'physical_display_verified':False,
        'gpu_scanout_timestamp_verified':False,
        'cross_mode_causal_latency_verified':False,
    }


class X11Window:
    """All Xlib calls stay on a single sampler thread."""
    def __init__(self, window):
        if not isinstance(window,str) or not window.isdecimal():
            raise ValueError('INVALID_WINDOW')
        self.window=int(window)
        if not 0<self.window<2**32:
            raise ValueError('INVALID_WINDOW')
        libname=ctypes.util.find_library('X11')
        if not libname:
            raise ValueError('X11_UNAVAILABLE')
        self.x=ctypes.CDLL(libname)
        P=ctypes.c_void_p; U=ctypes.c_ulong; I=ctypes.c_int
        self.x.XOpenDisplay.argtypes=[ctypes.c_char_p]
        self.x.XOpenDisplay.restype=P
        self.x.XCloseDisplay.argtypes=[P]
        self.x.XGetGeometry.argtypes=[P,U,ctypes.POINTER(U),ctypes.POINTER(I),
            ctypes.POINTER(I),ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint)]
        self.x.XGetGeometry.restype=I
        self.x.XGetImage.argtypes=[P,U,I,I,ctypes.c_uint,ctypes.c_uint,U,I]
        self.x.XGetImage.restype=P
        self.x.XGetPixel.argtypes=[P,I,I]
        self.x.XGetPixel.restype=U
        self.x.XDestroyImage.argtypes=[P]
        self.x.XDestroyImage.restype=I
        self.display=self.x.XOpenDisplay(None)
        if not self.display:
            raise ValueError('X11_UNAVAILABLE')
        try:
            root=U(); left=I(); top=I()
            w=ctypes.c_uint(); h=ctypes.c_uint()
            border=ctypes.c_uint(); depth=ctypes.c_uint()
            ok=self.x.XGetGeometry(self.display,self.window,ctypes.byref(root),
                ctypes.byref(left),ctypes.byref(top),ctypes.byref(w),
                ctypes.byref(h),ctypes.byref(border),ctypes.byref(depth))
            if not ok or (w.value,h.value)!=WINDOW_SIZE or depth.value!=24:
                raise ValueError('WINDOW_GEOMETRY_MISMATCH')
        except BaseException:
            self.close()
            raise

    def close(self):
        if getattr(self,'display',None):
            self.x.XCloseDisplay(self.display)
            self.display=None

    def sample(self):
        image=self.x.XGetImage(self.display,self.window,MIN_X,MIN_Y,
            MAX_X-MIN_X+1,MAX_Y-MIN_Y+1,ctypes.c_ulong(-1).value,2)
        if not image:
            raise ValueError('X11_CAPTURE_UNAVAILABLE')
        try:
            values={}
            for k,(x,y) in POINTS.items():
                p=self.x.XGetPixel(image,x-MIN_X,y-MIN_Y)
                # Pinned Xvfb 24-bit TrueColor uses 0xRRGGBB.
                # Background-color calibration is mandatory before success.
                values[k]=((p>>16)&255,(p>>8)&255,p&255)
            def rgb_at(pos):
                x,y=pos
                p=self.x.XGetPixel(image,x-MIN_X,y-MIN_Y)
                return ((p>>16)&255,(p>>8)&255,p&255)
            token=decode_frame_token([
                rgb_at(TOKEN_START),
                *(rgb_at(point) for point in TOKEN_BITS),
                rgb_at(TOKEN_END),
            ])
            if token is not None:
                values['frame_token_u16']=token
            return values
        finally:
            self.x.XDestroyImage(image)


class CounterWindowWatcher:
    def __init__(self,window,sampler_factory=X11Window,seconds=0.75):
        self.window=window
        self.factory=sampler_factory
        self.seconds=min(max(float(seconds),0.2),1.5)
        self.triggered=threading.Event()
        self._cancel_reason=''
        self.ready=threading.Event()
        self.finished=threading.Event()
        self._thread=None
        self._report=result(INCONCLUSIVE)
        self._frame_token=None
        self._host_command_complete_ns=None
        self._host_command_begin_ns=None
        self._sample_begin_ns=None
        self._sample_end_ns=None
        self._last_absent_begin_ns=None
        self._last_absent_end_ns=None
        self._last_absent_pixels=None
        self._post_trigger_absent_count=0
        self._x11_sample_sequence=[]

    def start(self):
        self._thread=threading.Thread(target=self._run,daemon=True)
        self._thread.start()
        # Arm well BEFORE the 116-tick ready marker, not after it.
        return self.ready.wait(0.35)

    def begin_keydown_command(self):
        # Called immediately BEFORE invoking the host xdotool subprocess,
        # not an actual host-HID or guest libnx delivery timestamp.
        self._host_command_begin_ns=time.monotonic_ns()

    def trigger(self):
        # Taken just AFTER successful xdotool keydown subprocess return,
        # on this host's monotonic clock. NOT a physical keydown timestamp.
        self._host_command_complete_ns=time.monotonic_ns()
        self.triggered.set()

    def cancel(self,reason='ZR_NOT_TRIGGERED'):
        self._cancel_reason=reason
        self.triggered.set()

    def finish(self):
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if not self.finished.is_set():
            return result(INCONCLUSIVE,reason='MONITOR_TIMEOUT')
        return self._report

    def frame_token_result(self):
        # Never assert guest frame identity without a guest trace CSV.
        ok=(self._report['status']==STATUS and
            type(self._frame_token) is int)
        return {
            'schema':'dino-nexium-host-frame-token-v1',
            'status':('HOST_X11_FRAME_TOKEN_OBSERVED_UNBOUND' if ok else
                      'INCONCLUSIVE_NO_X11_FRAME_TOKEN'),
            'token_u16':self._frame_token if ok else None,
            'token_same_x11_image_as_counter_pixels':ok,
            'guest_submitted_frame_identity_verified':False,
            'exact_host_guest_frame_latency_verified':False,
            'physical_display_verified':False,
        }

    def capture_interval_result(self):
        # Report a bounded host XGetImage *sampling interval*, not latency
        # to guest frame generation, presentation onset, LCD photons or HID.
        start=self._sample_begin_ns
        end=self._sample_end_ns
        origin=self._host_command_complete_ns
        valid=(self._report['status']==STATUS and
               type(self._frame_token) is int and
               type(origin) is int and type(start) is int and
               type(end) is int and
               0<=origin<=start<=end and
               0<=end-origin<=2_500_000_000)
        lower=(start-origin)//1000 if valid else None
        upper=(end-origin+999)//1000 if valid else None
        return {
            'schema':'dino-nexium-host-x11-sample-window-v1',
            'status':('HOST_COMMAND_COMPLETION_TO_X11_CAPTURE_WINDOW_WITNESSED'
                      if valid else 'INCONCLUSIVE_NO_BOUND_X11_CAPTURE_WINDOW'),
            'host_x11_capture_window_observed':bool(valid),
            'frame_token_u16':self._frame_token if valid else None,
            'post_keydown_command_to_capture_begin_us':lower,
            'post_keydown_command_to_capture_end_us':upper,
            'xgetimage_call_duration_upper_us':upper-lower if valid else None,
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'precise_input_to_display_latency_verified':False,
            'actual_guest_input_delivery_timestamp_verified':False,
            'physical_controller_verified':False,
            'physical_display_verified':False,
            'gpu_scanout_timestamp_verified':False,
        }

    def command_bracket_result(self):
        # Both host xdotool execution and the actual XGetImage call
        # are bracketed on the same host-only monotonic clock.
        started=self._host_command_begin_ns
        completed=self._host_command_complete_ns
        first=self._sample_begin_ns
        last=self._sample_end_ns
        valid=(self._report['status']==STATUS and
               type(self._frame_token) is int and
               all(type(v) is int for v in (started,completed,first,last)) and
               0<=started<=completed<=first<=last and
               last-started<=2_500_000_000)
        begin=(first-started)//1000 if valid else None
        end=(last-started+999)//1000 if valid else None
        completed_start=(first-completed)//1000 if valid else None
        completed_end=(last-completed+999)//1000 if valid else None
        cmd_ns=(completed-started) if valid else None
        return {
            'schema':'dino-nexium-host-keydown-call-capture-v1',
            'status':('HOST_KEYDOWN_COMMAND_AND_X11_SAMPLE_BRACKET_WITNESSED'
                      if valid else 'INCONCLUSIVE_NO_HOST_KEYDOWN_BRACKET'),
            'host_command_to_x11_bracket_observed':bool(valid),
            'host_frame_token_u16':self._frame_token if valid else None,
            'keydown_command_duration_floor_us':cmd_ns//1000 if valid else None,
            'keydown_command_duration_ceil_us':(cmd_ns+999)//1000 if valid else None,
            'keydown_call_begin_to_x11_begin_us':begin,
            'keydown_call_begin_to_x11_end_us':end,
            'keydown_call_complete_to_x11_begin_us':completed_start,
            'keydown_call_complete_to_x11_end_us':completed_end,
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'guest_input_delivery_timestamp_verified':False,
            'first_visible_frame_onset_verified':False,
            'physical_joycon_latency_verified':False,
            'physical_switch_lcd_latency_verified':False,
            'gpu_scanout_timestamp_verified':False,
            'cross_mode_causal_comparison_verified':False,
        }

    def transition_bracket_result(self):
        # A conservative observation interval, not a presentation-onset time.
        # Use only negative and positive samples AFTER host keydown return.
        begin=self._host_command_begin_ns
        completed=self._host_command_complete_ns
        negative_start=self._last_absent_begin_ns
        negative_end=self._last_absent_end_ns
        positive_start=self._sample_begin_ns
        positive_end=self._sample_end_ns
        negative=self._last_absent_pixels
        valid=(self._report['status']==STATUS and
               type(self._frame_token) is int and
               all(type(v) is int for v in (
                   begin,completed,negative_start,negative_end,
                   positive_start,positive_end)) and
               0<=begin<=completed<=negative_start<=negative_end<=
                  positive_start<=positive_end and
               positive_end-begin<=2_500_000_000 and
               type(self._post_trigger_absent_count) is int and
               1<=self._post_trigger_absent_count<=199 and
               type(negative) is dict and
               all(k in negative and
                   isinstance(negative[k],(tuple,list)) and
                   len(negative[k])==3 and
                   all(type(v) is int and 0<=v<=255
                       for v in negative[k])
                   for k in POINTS) and
               not all(tuple(negative[k])==rgb
                       for k,rgb in EXPECTED.items()))
        offsets=(
            ((negative_start-begin)//1000,
             (negative_end-begin+999)//1000,
             (positive_start-begin)//1000,
             (positive_end-begin+999)//1000)
            if valid else (None,None,None,None))
        return {
            'schema':'dino-nexium-host-x11-transition-bracket-v1',
            'status':('HOST_X11_ABSENT_TO_COUNTER_FRAME_SAMPLE_BRACKET_OBSERVED'
                      if valid else 'INCONCLUSIVE_NO_POST_TRIGGER_ABSENT_SAMPLE'),
            'post_trigger_absent_x11_images':(
                self._post_trigger_absent_count if valid else 0),
            'host_x11_transition_sample_bracket_observed':bool(valid),
            'x11_positive_frame_token_u16':self._frame_token if valid else None,
            'last_negative_x11_pixel_rgb':(
                {k:list(negative[k]) for k in POINTS} if valid else None),
            'last_negative_xgetimage_begin_offset_us':offsets[0],
            'last_negative_xgetimage_end_offset_us':offsets[1],
            'first_positive_xgetimage_begin_offset_us':offsets[2],
            'first_positive_xgetimage_end_offset_us':offsets[3],
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'first_visible_frame_onset_verified':False,
            'precise_input_to_display_latency_verified':False,
            'guest_input_delivery_timestamp_verified':False,
            'physical_controller_verified':False,
            'physical_display_verified':False,
            'gpu_scanout_timestamp_verified':False,
            'cross_mode_causal_comparison_verified':False,
        }

    def sample_sequence_result(self):
        # A compact, bounded X11 sample log: four calibrated RGB triplets
        # per image, time offsets, no full screenshots or host window IDs.
        trace=self._x11_sample_sequence
        matched=(self._report['status']==STATUS and
                 type(self._frame_token) is int and
                 len(trace)==self._post_trigger_absent_count+1 and
                 2<=len(trace)<=199 and
                 all(type(entry['counter_four_pixels_present']) is bool and
                     entry['counter_four_pixels_present'] is False
                     for entry in trace[:-1]) and
                 trace[-1]['counter_four_pixels_present'] is True and
                 trace[-1]['frame_token_u16']==self._frame_token and
                 self._host_command_begin_ns is not None)
        return {
            'schema':'dino-nexium-host-x11-sample-sequence-v1',
            'status':('HOST_X11_ORDERED_SAMPLES_OBSERVED_UNBOUND' if matched
                      else 'INCONCLUSIVE_NO_ORDERED_X11_SAMPLE_SEQUENCE'),
            'ordered_host_x11_samples_observed':bool(matched),
            'post_command_negative_samples':(
                self._post_trigger_absent_count if matched else 0),
            'matching_positive_frame_token_u16':(
                self._frame_token if matched else None),
            'samples':list(trace) if matched else [],
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'precise_first_visible_frame_onset_verified':False,
            'guest_input_delivery_timestamp_verified':False,
            'physical_controller_verified':False,
            'physical_display_verified':False,
            'gpu_scanout_timestamp_verified':False,
            'cross_mode_causal_latency_verified':False,
        }

    def _run(self):
        sampler=None
        count=0
        pre=None
        post=[]
        reason=''
        try:
            sampler=self.factory(self.window)
            pre=sampler.sample()
            count+=1
            self.ready.set()
            # Allow the original ROM-free AI 116-tick pursuit to finish
            # without a new host timing race. Cancel on absent ready marker.
            if self.triggered.wait(timeout=26.0):
                if self._cancel_reason:
                    reason=self._cancel_reason
                else:
                    until=time.monotonic()+self.seconds
                    while time.monotonic()<until and count<200:
                        started_ns=time.monotonic_ns()
                        sample=sampler.sample()
                        ended_ns=time.monotonic_ns()
                        count+=1
                        post.append(sample)
                        # Every genuine post-command X11 image is recorded
                        # BEFORE choosing an exit for the first positive.
                        # Keep bounded 4-point RGB values, host-relative
                        # microseconds and optional 16-bit frame token only.
                        if (type(self._host_command_begin_ns) is int and
                            started_ns>=self._host_command_begin_ns and
                            all(k in sample and
                                isinstance(sample[k],(list,tuple)) and
                                len(sample[k])==3 and
                                all(type(v) is int and 0<=v<=255
                                    for v in sample[k])
                                for k in POINTS) and
                            len(self._x11_sample_sequence)<199):
                            positive=classify(pre,[sample])==STATUS
                            self._x11_sample_sequence.append({
                                'index':len(self._x11_sample_sequence)+1,
                                'capture_begin_offset_us':
                                    (started_ns-self._host_command_begin_ns)//1000,
                                'capture_end_offset_us':
                                    (ended_ns-self._host_command_begin_ns+999)//1000,
                                'counter_four_pixels_present':positive,
                                'four_counter_point_rgb':{
                                    k:list(sample[k]) for k in POINTS},
                                'frame_token_u16':(
                                    sample.get('frame_token_u16')
                                    if positive and
                                       type(sample.get('frame_token_u16')) is int
                                    else None),
                            })
                        if classify(pre,[sample])==STATUS:
                            candidate=sample.get('frame_token_u16')
                            if type(candidate) is int and 0<=candidate<=65535:
                                self._frame_token=candidate
                                self._sample_begin_ns=started_ns
                                self._sample_end_ns=ended_ns
                            break
                        # Capture last genuine nonmatching X11 image, not
                        # a fabricated timestamp or the pre-trigger image.
                        # This snapshot came from the SAME XGetImage call
                        # which tested the counter's four pixel colors.
                        if all(k in sample and isinstance(sample[k],(list,tuple))
                               and len(sample[k])==3
                               for k in POINTS):
                            self._last_absent_begin_ns=started_ns
                            self._last_absent_end_ns=ended_ns
                            self._last_absent_pixels={
                                k:tuple(sample[k]) for k in POINTS}
                            self._post_trigger_absent_count+=1
                        time.sleep(0.008)
            else:
                reason='ZR_NOT_TRIGGERED'
        except (ValueError,OSError) as exc:
            reason=str(exc) if str(exc) in {
                'INVALID_WINDOW','X11_UNAVAILABLE','WINDOW_GEOMETRY_MISMATCH',
                'X11_CAPTURE_UNAVAILABLE'} else 'X11_ERROR'
        except Exception:
            reason='X11_ERROR'
        finally:
            if sampler is not None:
                sampler.close()
            self.ready.set()
            status=classify(pre,post)
            if status!=STATUS and not reason:
                reason='PIXELS_NOT_OBSERVED'
            self._report=result(status,count,pre is not None and
                tuple(pre.get('ground',()))==EXPECTED['ground'],reason)
            self.finished.set()


def save(path,record):
    from pathlib import Path
    Path(path).write_text(json.dumps(record,sort_keys=True)+'\n',encoding='ascii')

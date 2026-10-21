#!/usr/bin/env python3
"""Stage298: select a private dino replay window with active INP transitions.

This inspects only locally supplied WolfMAME-family INP/WLF files; never
prints button bytes, port values, user paths or private file hashes.
The 0.106 port offsets are SOURCE-INFERRED, not authenticated WolfMAME
controller mapping. The selected windows remain *candidate* callback
indices, not verified causal alignment with INP record numbers.
"""
from collections import deque
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import wolfmame0106_dino_input_reference as inp_ref
    from . import wolfmame0106_private_mng_capture as capture
    from . import wolfmame0106_private_window_overlap as overlap
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import wolfmame0106_dino_input_reference as inp_ref
    import wolfmame0106_private_mng_capture as capture
    import wolfmame0106_private_window_overlap as overlap

# Input mappings come from the structural dino INP layout. These are
# hypotheses about a WolfMAME recording, NOT independently proven controls.
# Movement transitions each carry weight 1, attack and jump carry weight 4.
# START1 gives weight 2. No other player or coin data is retained.
PRIVATE_SIGNALS = (
    (inp_ref.PORTS["p1"], 0x0F, 1),
    (inp_ref.PORTS["p1"], 0x30, 4),
    (inp_ref.PORTS["p2"], 0x0F, 1),
    (inp_ref.PORTS["p2"], 0x30, 4),
    (inp_ref.PORTS["system"], 0x10, 2),
)
MAX_EDGES_PER_RECORD = 13
MAX_WEIGHT_PER_RECORD = 4 * 4 + 8 * 1 + 2  # two players with two actions each


def _check_window(frames, shift, minimum_edges, recorded_frames):
    if (type(frames) is not int or
            not 2 <= frames <= capture.MAX_FRAMES or
            type(shift) is not int or
            not overlap.MIN_OVERLAP <= shift < frames or
            frames - shift < overlap.MIN_OVERLAP or
            type(minimum_edges) is not int or
            not 1 <= minimum_edges <= 64 or
            type(recorded_frames) is not int or
            recorded_frames < frames + shift):
        raise ValueError("invalid private auto-window parameters")


def _score_record(previous, current):
    """Return (source-inferred press onsets, weighted activity), no raw bytes."""
    edges = 0
    weight = 0
    for offset, mask, unit_weight in PRIVATE_SIGNALS:
        # Detect transitions high->low only. The record has active-low
        # control bits in the upstream CPS-1 mapping.
        pressed = (previous[offset] & ~current[offset]) & mask
        edges += pressed.bit_count()
        weight += unit_weight * pressed.bit_count()
    return edges, weight


def select(inp, wlf, *, frames, shift, minimum_edges=3):
    """Pick earliest maximum-scoring overlap, with bounded scan memory.

    Returns only (candidate_first_callback_start, overlap_onset_count).
    Fail closed for recordings without enough inferred input activity.
    """
    inp, wlf = Path(inp), Path(wlf)
    n, version, _duration = gate.private_inputs(inp, wlf)
    if not version.startswith("0.106 "):
        raise ValueError("unsupported private recording revision")
    _check_window(frames, shift, minimum_edges, n)
    if inp.stat().st_size > capture.MAX_INP_BYTES:
        raise ValueError("private INP exceeds safe scan size")
    window = frames - shift
    last_possible_start = n - (frames + shift)
    before = inp.stat()
    counts = deque()
    total_edges = 0
    total_weight = 0
    best_score = -1
    best_edges = -1
    best_start = None
    previous = None
    with inp.open("rb") as stream:
        header = stream.read(inp_ref.HEADER_BYTES)
        if len(header) != inp_ref.HEADER_BYTES or header[:4] != b"dino":
            raise ValueError("private dino header changed before scan")
        for frame_index in range(last_possible_start + frames):
            row = stream.read(inp_ref.FRAME_BYTES)
            if len(row) != inp_ref.FRAME_BYTES:
                raise ValueError("private recording truncated during scan")
            if previous is None:
                edges, weight = 0, 0
            else:
                edges, weight = _score_record(previous, row)
            previous = row
            counts.append((edges, weight))
            total_edges += edges
            total_weight += weight
            if len(counts) > window:
                old_edges, old_weight = counts.popleft()
                total_edges -= old_edges
                total_weight -= old_weight
            if frame_index < frames - 1:
                continue
            candidate_start = frame_index + 1 - frames
            if candidate_start > last_possible_start:
                break
            # Weight controls for activity, but require multiple *distinct*
            # rising signals to prevent a single spurious press.
            if total_edges < minimum_edges:
                continue
            if (total_weight > best_score or
                    (total_weight == best_score and total_edges > best_edges)):
                best_score = total_weight
                best_edges = total_edges
                best_start = candidate_start
    after = inp.stat()
    if (before.st_size != after.st_size or
            before.st_mtime_ns != after.st_mtime_ns or
            before.st_ctime_ns != after.st_ctime_ns):
        raise ValueError("private input changed during auto-window selection")
    if best_start is None:
        raise ValueError("no sufficiently active candidate overlap")
    if not (0 <= best_start <= overlap.MAX_START and
            best_start + shift + frames <= n and
            minimum_edges <= best_edges <= MAX_EDGES_PER_RECORD * window):
        raise ValueError("selected source-inferred window is invalid")
    return best_start, best_edges

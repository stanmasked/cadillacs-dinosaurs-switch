#!/usr/bin/env python3
"""Stage321: private NeXium optical capture through Xlib, no external xdotool/import.

The title AND client-supplied X11 _NET_WM_PID must match the particular
emulator process started by our private Stage316 host probe. X11 PIDs are
NOT cryptographically authenticated. All frames remain in memory and
no screenshot, original ROM byte or pixel is persisted by this module.
"""
import os

try:
    from . import nexium_x11_process_window_319 as ownership
except ImportError:
    import nexium_x11_process_window_319 as ownership

MAX_WINDOWS = 512
MAX_DEPTH = 10
MAX_PIXELS = 1920 * 1200


def _name(window, connection):
    title = window.get_wm_name()
    if isinstance(title, bytes):
        title = title.decode("utf-8", "replace")
    if not isinstance(title, str) or not title:
        atom = connection.intern_atom("_NET_WM_NAME", only_if_exists=True)
        if atom:
            prop = window.get_full_property(atom, 0)
            if prop is not None:
                data = prop.value
                title = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
    return title if isinstance(title, str) else ""


def _owner(window, connection):
    from Xlib import X
    atom = connection.intern_atom("_NET_WM_PID", only_if_exists=True)
    if not atom:
        return None
    prop = window.get_full_property(atom, X.AnyPropertyType)
    if prop is None or prop.format != 32 or len(prop.value) != 1:
        return None
    pid = int(prop.value[0])
    return pid if 1 < pid <= 2**31 - 1 else None


def _find_windows(connection, pid, *, parent_for=None):
    """Enumerate bounded visible windows; require exactly ONE process-bound hit."""
    from Xlib import X
    if type(pid) is not int or pid <= 1:
        return []
    if parent_for is None:
        parent_for = ownership._parent_linux
    queue = [(connection.screen().root, 0)]
    visited = set()
    matches = []
    while queue:
        if len(queue) > MAX_WINDOWS or len(visited) >= MAX_WINDOWS:
            return []
        window, depth = queue.pop(0)
        if window.id in visited:
            continue
        visited.add(window.id)
        try:
            attributes = window.get_attributes()
            if attributes.map_state != X.IsViewable:
                continue
            title = _name(window, connection)
            if "nexium" in title.lower():
                owner = _owner(window, connection)
                if owner is not None and ownership.belongs_to_run(
                        owner, pid, parent_for=parent_for):
                    matches.append(window)
                    if len(matches) > 1:
                        return []
            if depth < MAX_DEPTH:
                descendants = window.query_tree().children
                if len(descendants) > MAX_WINDOWS - len(visited):
                    return []
                queue.extend((child, depth+1) for child in descendants)
        except Exception:
            # A destroyed X11 window or malformed client properties are
            # inconclusive rather than allowing any unbound capture.
            return []
    return matches if len(matches) == 1 else []


def _capture(window, Image):
    """Get raw pixels FROM X11; do not reuse any supplied PIL reference frame."""
    from Xlib import X
    geometry = window.get_geometry()
    w, h = geometry.width, geometry.height
    if not (200 <= w <= 1920 and 200 <= h <= 1200 and
            w*h <= MAX_PIXELS and geometry.depth == 24):
        raise ValueError("unsupported host X11 capture geometry/depth")
    captured = window.get_image(0, 0, w, h, X.ZPixmap, 0xffffffff)
    if captured is None or captured.depth != 24 or len(captured.data) != w*h*4:
        raise ValueError("unsupported host X11 server pixel layout")
    return Image.frombytes("RGB", (w,h), captured.data, "raw", "BGRX")


def capture_process_window(pid, *, display_factory=None, parent_for=None,
                           image_module=None):
    """Return real visible host pixels or None; every X11 resource is released.

    The private caller still independently verifies dual optical beacons,
    frame-ID barcode and 10+ actual reference pixels for each guest row.
    """
    if type(pid) is not int or pid <= 1:
        return None
    if display_factory is None:
        from Xlib import display
        display_factory = display.Display
    if image_module is None:
        from PIL import Image
        image_module = Image
    server = None
    try:
        server = display_factory()
        matches = _find_windows(server, pid, parent_for=parent_for)
        if len(matches) != 1:
            return None
        return _capture(matches[0], image_module)
    except Exception:
        return None
    finally:
        if server is not None:
            server.close()

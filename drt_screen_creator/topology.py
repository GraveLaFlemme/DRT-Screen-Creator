from __future__ import annotations

import ctypes
import hashlib
import json
import sys
from ctypes import wintypes
from typing import Iterable

from .models import CaptureRegion, MonitorInfo


MONITORINFOF_PRIMARY = 0x00000001
MDT_EFFECTIVE_DPI = 0


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MonitorInfoEx(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class _Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def enumerate_monitors() -> list[MonitorInfo]:
    if sys.platform != "win32":
        raise RuntimeError("DRT Screen Creator nécessite Windows.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shcore = None
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.GetDpiForMonitor.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)]
        shcore.GetDpiForMonitor.restype = ctypes.c_long
    except (OSError, AttributeError):
        shcore = None

    monitors: list[MonitorInfo] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(_Rect),
        wintypes.LPARAM,
    )

    def callback(
        monitor_handle: wintypes.HMONITOR,
        _device_context: wintypes.HDC,
        _rect: ctypes.POINTER(_Rect),
        _data: wintypes.LPARAM,
    ) -> bool:
        info = _MonitorInfoEx()
        info.cbSize = ctypes.sizeof(_MonitorInfoEx)
        if not user32.GetMonitorInfoW(monitor_handle, ctypes.byref(info)):
            return True

        dpi_x = wintypes.UINT(96)
        dpi_y = wintypes.UINT(96)
        if shcore is not None:
            result = shcore.GetDpiForMonitor(
                monitor_handle,
                MDT_EFFECTIVE_DPI,
                ctypes.byref(dpi_x),
                ctypes.byref(dpi_y),
            )
            if result != 0:
                dpi_x.value = dpi_y.value = 96

        rect = info.rcMonitor
        monitors.append(
            MonitorInfo(
                name=str(info.szDevice),
                left=int(rect.left),
                top=int(rect.top),
                width=int(rect.right - rect.left),
                height=int(rect.bottom - rect.top),
                dpi_x=int(dpi_x.value),
                dpi_y=int(dpi_y.value),
                primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
            )
        )
        return True

    callback_ref = callback_type(callback)
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(_Rect), callback_type, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    if not user32.EnumDisplayMonitors(None, None, callback_ref, 0):
        error = ctypes.get_last_error()
        raise OSError(error, "Impossible d’énumérer les écrans Windows.")
    return sorted(monitors, key=lambda monitor: (monitor.left, monitor.top, monitor.name.casefold()))


def topology_fingerprint(monitors: Iterable[MonitorInfo]) -> str:
    payload = [
        monitor.fingerprint_dict()
        for monitor in sorted(monitors, key=lambda item: (item.name.casefold(), item.left, item.top))
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def virtual_bounds(monitors: Iterable[MonitorInfo]) -> CaptureRegion:
    items = list(monitors)
    if not items:
        raise ValueError("Aucun écran détecté.")
    left = min(item.left for item in items)
    top = min(item.top for item in items)
    right = max(item.left + item.width for item in items)
    bottom = max(item.top + item.height for item in items)
    return CaptureRegion(left, top, right - left, bottom - top)


def region_coverage(region: CaptureRegion, monitors: Iterable[MonitorInfo]) -> float:
    if not region.is_valid:
        return 0.0
    covered = 0
    for monitor in monitors:
        overlap = region.intersection(monitor.region)
        if overlap:
            covered += overlap.width * overlap.height
    return min(1.0, covered / (region.width * region.height))


def region_is_visible(region: CaptureRegion, monitors: Iterable[MonitorInfo]) -> bool:
    return any(region.intersects(monitor.region) for monitor in monitors)


def get_cursor_position() -> tuple[int, int]:
    if sys.platform != "win32":
        raise RuntimeError("Cette fonction nécessite Windows.")
    point = _Point()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if not user32.GetCursorPos(ctypes.byref(point)):
        error = ctypes.get_last_error()
        raise OSError(error, "Position de la souris indisponible.")
    return int(point.x), int(point.y)


def exclude_window_from_capture(window_id: int) -> bool:
    if sys.platform != "win32" or not window_id:
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    set_affinity = getattr(user32, "SetWindowDisplayAffinity", None)
    if set_affinity is None:
        return False
    set_affinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    set_affinity.restype = wintypes.BOOL
    # WDA_EXCLUDEFROMCAPTURE, disponible sur les versions Windows 10 récentes.
    return bool(set_affinity(wintypes.HWND(window_id), wintypes.DWORD(0x00000011)))

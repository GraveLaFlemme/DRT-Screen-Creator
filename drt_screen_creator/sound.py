from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
from typing import Callable


MciCommand = Callable[[str], int]


def send_mci_command(command: str) -> int:
    """Envoie une commande audio asynchrone au lecteur multimédia de Windows."""
    if sys.platform != "win32":
        return 1
    winmm = ctypes.WinDLL("winmm", use_last_error=True)
    sender = winmm.mciSendStringW
    sender.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HWND]
    sender.restype = wintypes.UINT
    return int(sender(command, None, 0, None))


class SuccessSound:
    """Joue le MP3 DRT fourni, sans bloquer l’interface."""

    def __init__(self, sound_path: Path | None = None, sender: MciCommand | None = None) -> None:
        self.sound_path = sound_path
        self._send = sender or send_mci_command
        self._alias = f"drt_capture_sound_{id(self):x}"
        self._opened = False

    def play(self) -> bool:
        if self.sound_path is None or not self.sound_path.is_file():
            return False
        if not self._opened:
            command = f'open "{self.sound_path.resolve()}" type mpegvideo alias {self._alias}'
            if self._send(command) != 0:
                return False
            self._opened = True
        else:
            self._send(f"stop {self._alias}")

        if self._send(f"seek {self._alias} to start") != 0:
            self.close()
            return False
        return self._send(f"play {self._alias}") == 0

    def close(self) -> None:
        if not self._opened:
            return
        self._send(f"stop {self._alias}")
        self._send(f"close {self._alias}")
        self._opened = False

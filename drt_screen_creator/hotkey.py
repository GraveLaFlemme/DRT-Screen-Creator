from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HOTKEY_ID_FIXED = 0x445254  # "DRT"
HOTKEY_ID_FREE = HOTKEY_ID_FIXED + 1


class InvalidHotkey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HotkeySpec:
    modifiers: int
    virtual_key: int
    canonical: str


_MODIFIER_ALIASES = {
    "ctrl": ("Ctrl", MOD_CONTROL),
    "control": ("Ctrl", MOD_CONTROL),
    "alt": ("Alt", MOD_ALT),
    "shift": ("Shift", MOD_SHIFT),
    "maj": ("Shift", MOD_SHIFT),
    "meta": ("Win", MOD_WIN),
    "win": ("Win", MOD_WIN),
    "windows": ("Win", MOD_WIN),
}
_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")
_RESERVED = {"Alt+F4", "Win+D", "Win+L", "Win+R"}


def parse_hotkey(value: str) -> HotkeySpec:
    normalized = value.replace(" ", "")
    parts = [part for part in normalized.split("+") if part]
    if not parts:
        raise InvalidHotkey("Choisissez un raccourci clavier.")

    modifier_names: set[str] = set()
    modifiers = 0
    key_name = ""
    virtual_key = 0

    for raw_part in parts:
        part = raw_part.casefold()
        modifier = _MODIFIER_ALIASES.get(part)
        if modifier:
            modifier_names.add(modifier[0])
            modifiers |= modifier[1]
            continue
        if key_name:
            raise InvalidHotkey("Le raccourci doit contenir une seule touche principale.")
        upper = raw_part.upper()
        function_match = re.fullmatch(r"F([1-9]|1[0-2])", upper)
        if function_match:
            key_name = upper
            virtual_key = 0x70 + int(function_match.group(1)) - 1
        elif re.fullmatch(r"[A-Z0-9]", upper):
            key_name = upper
            virtual_key = ord(upper)
        else:
            raise InvalidHotkey("Utilisez une lettre, un chiffre ou une touche F1 à F12.")

    if not key_name:
        raise InvalidHotkey("Le raccourci ne contient pas de touche principale.")
    if not modifier_names and not key_name.startswith("F"):
        raise InvalidHotkey("Une lettre ou un chiffre doit être associé à Ctrl, Alt, Maj ou Win.")

    ordered = [name for name in _MODIFIER_ORDER if name in modifier_names]
    canonical = "+".join([*ordered, key_name])
    if canonical in _RESERVED:
        raise InvalidHotkey("Ce raccourci est réservé par Windows.")
    return HotkeySpec(modifiers=modifiers, virtual_key=virtual_key, canonical=canonical)


class _HotkeySignals(QObject):
    activated = Signal()
    free_activated = Signal()


class GlobalHotkeyManager(QAbstractNativeEventFilter):
    def __init__(self, application: QObject) -> None:
        super().__init__()
        self.signals = _HotkeySignals()
        self._application = application
        self._registered = False
        self._spec: HotkeySpec | None = None
        self._free_spec: HotkeySpec | None = None
        application.installNativeEventFilter(self)

    @property
    def is_registered(self) -> bool:
        return self._registered

    @property
    def current_hotkey(self) -> str:
        return self._spec.canonical if self._spec else ""

    @property
    def current_free_hotkey(self) -> str:
        return self._free_spec.canonical if self._free_spec else ""

    def register(self, value: str) -> tuple[bool, str]:
        """Enregistre uniquement le raccourci fixe (compatibilité interne/tests)."""
        if sys.platform != "win32":
            return False, "Les raccourcis globaux nécessitent Windows."
        try:
            spec = parse_hotkey(value)
        except InvalidHotkey as error:
            return False, str(error)

        self.unregister()
        success, error = self._register_spec(HOTKEY_ID_FIXED, spec)
        if success:
            self._registered = True
            self._spec = spec
        return success, error

    def register_pair(self, fixed_value: str, free_value: str) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "Les raccourcis globaux nécessitent Windows."
        try:
            fixed_spec = parse_hotkey(fixed_value)
            free_spec = parse_hotkey(free_value)
        except InvalidHotkey as error:
            return False, str(error)
        if fixed_spec.canonical == free_spec.canonical:
            return False, "Les deux raccourcis doivent être différents."

        self.unregister()
        success, error = self._register_spec(HOTKEY_ID_FIXED, fixed_spec)
        if not success:
            return False, f"Zone prédéfinie : {error}"
        success, error = self._register_spec(HOTKEY_ID_FREE, free_spec)
        if not success:
            self._unregister_id(HOTKEY_ID_FIXED)
            return False, f"Capture libre : {error}"

        self._registered = True
        self._spec = fixed_spec
        self._free_spec = free_spec
        return True, ""

    @staticmethod
    def _register_spec(hotkey_id: int, spec: HotkeySpec) -> tuple[bool, str]:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        success = user32.RegisterHotKey(
            None,
            hotkey_id,
            spec.modifiers | MOD_NOREPEAT,
            spec.virtual_key,
        )
        if not success:
            error = ctypes.get_last_error()
            if error == 1409:
                return False, "Ce raccourci est déjà utilisé par une autre application."
            return False, f"Impossible d’activer ce raccourci Windows (erreur {error})."
        return True, ""

    def unregister(self) -> None:
        if not self._registered or sys.platform != "win32":
            self._registered = False
            self._spec = None
            self._free_spec = None
            return
        self._unregister_id(HOTKEY_ID_FIXED)
        if self._free_spec is not None:
            self._unregister_id(HOTKEY_ID_FREE)
        self._registered = False
        self._spec = None
        self._free_spec = None

    @staticmethod
    def _unregister_id(hotkey_id: int) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey(None, hotkey_id)

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - API Qt
        if self._registered and bytes(event_type) in {b"windows_dispatcher_MSG", b"windows_generic_MSG"}:
            native_message = wintypes.MSG.from_address(int(message))
            if native_message.message == WM_HOTKEY:
                if native_message.wParam == HOTKEY_ID_FIXED:
                    self.signals.activated.emit()
                    return True
                if native_message.wParam == HOTKEY_ID_FREE:
                    self.signals.free_activated.emit()
                    return True
        return False

    def close(self) -> None:
        self.unregister()
        try:
            self._application.removeNativeEventFilter(self)
        except RuntimeError:
            pass

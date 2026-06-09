"""Global hotkey manager using Windows RegisterHotKey API.

RegisterHotKey is far more reliable than SetWindowsHookEx-based libraries
(keyboard, pynput) on Windows 10/11 — no background threads, no admin
rights, and no PyInstaller bundling headaches.

A tiny, off-screen Tool QWidget receives WM_HOTKEY messages via Qt's
native event loop.  Callbacks are invoked on the Qt main thread, so they
may call Qt APIs directly without signal indirection (though using signals
is still fine).

Supported combo syntax examples:
    "ctrl+shift+f9"   "win+h"   "ctrl+alt+r"   "ctrl+shift+a"
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes   # must be imported explicitly; ctypes.wintypes is not auto-loaded
from collections.abc import Callable
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

# use_last_error=True captures GetLastError() into Python thread-local storage.
_user32 = ctypes.WinDLL("user32", use_last_error=True)

# Declare argtypes so ctypes uses the correct widths on 64-bit Windows.
# HWND is pointer-sized; without argtypes ctypes defaults to c_int (32-bit).
_user32.RegisterHotKey.argtypes = [
    ctypes.wintypes.HWND,   # hWnd       (NULL or a real window)
    ctypes.c_int,            # id
    ctypes.c_uint,           # fsModifiers
    ctypes.c_uint,           # vk
]
_user32.RegisterHotKey.restype  = ctypes.wintypes.BOOL

_user32.UnregisterHotKey.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.c_int,
]
_user32.UnregisterHotKey.restype = ctypes.wintypes.BOOL

# ── Windows API constants ──────────────────────────────────────────────────
WM_HOTKEY    = 0x0312
MOD_ALT      = 0x0001
MOD_CONTROL  = 0x0002
MOD_SHIFT    = 0x0004
MOD_WIN      = 0x0008
MOD_NOREPEAT = 0x4000   # suppress auto-repeat while key is held down

# ── Virtual-key code table ─────────────────────────────────────────────────
_VK: dict[str, int] = {
    # Function keys
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    # Navigation / editing
    "space": 0x20, "enter": 0x0D, "return": 0x0D,
    "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "ins": 0x2D,
    "home": 0x24, "end": 0x23,
    "page_up": 0x21, "pageup": 0x21, "pgup": 0x21,
    "page_down": 0x22, "pagedown": 0x22, "pgdn": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}

_MOD_NAMES: dict[str, int] = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT,
    "win": MOD_WIN, "windows": MOD_WIN,
    "left windows": MOD_WIN, "right windows": MOD_WIN,
}


def _parse_combo(combo: str) -> tuple[int, int]:
    """Parse 'ctrl+shift+f9' → (modifier_flags, vkey_code).

    Raises ValueError on unknown key names or missing main key.
    """
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    mods = 0
    vkey = 0
    for p in parts:
        if p in _MOD_NAMES:
            mods |= _MOD_NAMES[p]
        elif p in _VK:
            if vkey:
                raise ValueError(f"Multiple non-modifier keys in combo: '{combo}'")
            vkey = _VK[p]
        elif len(p) == 1 and p.isalpha():
            if vkey:
                raise ValueError(f"Multiple non-modifier keys in combo: '{combo}'")
            vkey = ord(p.upper())   # A(0x41) … Z(0x5A)
        elif len(p) == 1 and p.isdigit():
            if vkey:
                raise ValueError(f"Multiple non-modifier keys in combo: '{combo}'")
            vkey = ord(p)           # 0x30 … 0x39
        else:
            raise ValueError(f"Unknown key name '{p}' in combo: '{combo}'")
    if not vkey:
        raise ValueError(f"No main key found in combo: '{combo}'")
    return mods, vkey


class _MSG(ctypes.Structure):
    """Minimal Windows MSG structure used when casting nativeEvent message."""
    _fields_ = [
        ("hwnd",    ctypes.c_size_t),
        ("message", ctypes.c_uint),
        ("wParam",  ctypes.c_size_t),
        ("lParam",  ctypes.c_size_t),
        ("time",    ctypes.c_ulong),
        ("x",       ctypes.c_long),
        ("y",       ctypes.c_long),
    ]


class _HotkeyReceiver(QWidget):
    """Invisible off-screen Tool window that receives WM_HOTKEY messages.

    Placed far off-screen at (-32000, -32000) with size 1×1.  The Tool
    window type ensures no taskbar button.  show() is called to guarantee
    Qt allocates a native HWND and routes messages to nativeEvent(); it is
    immediately hidden so the user never sees it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(1, 1)
        self.move(-32000, -32000)
        # show() then hide(): HWND is fully initialised and Qt's event loop
        # continues processing its message queue even while hidden.
        self.show()
        self.hide()
        self._hwnd: int = int(self.winId())
        self._callbacks: dict[int, Callable] = {}
        self._next_id: int = 0xC001   # above the system-reserved range

    # ── internal ────────────────────────────────────────────────────────────

    def _do_register(self, mods: int, vkey: int, callback: Callable) -> int:
        id_ = self._next_id
        self._next_id += 1
        ok = _user32.RegisterHotKey(self._hwnd, id_, mods | MOD_NOREPEAT, vkey)
        if not ok:
            err = ctypes.get_last_error()
            raise RuntimeError(
                f"RegisterHotKey 失敗 (error {err}) "
                f"— vk={vkey:#04x} mod={mods:#06x}  "
                f"このキーは他のアプリが使用中の可能性があります"
            )
        self._callbacks[id_] = callback
        return id_

    def _do_unregister(self, id_: int) -> None:
        _user32.UnregisterHotKey(self._hwnd, id_)
        self._callbacks.pop(id_, None)

    def _unregister_all(self) -> None:
        for id_ in list(self._callbacks):
            _user32.UnregisterHotKey(self._hwnd, id_)
        self._callbacks.clear()

    # ── Qt override — WM_HOTKEY arrives here on the main thread ─────────────

    def nativeEvent(self, event_type: bytes, message) -> tuple[bool, int]:  # type: ignore[override]
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message == WM_HOTKEY:
                cb = self._callbacks.get(int(msg.wParam))
                if cb is not None:
                    try:
                        cb()
                    except Exception:
                        pass
                    return True, 0
        return super().nativeEvent(event_type, message)


class HotkeyManager:
    """Public API for named global hotkeys.

    Usage::

        mgr = HotkeyManager()
        mgr.bind("record", "ctrl+shift+f9", my_callback)
        # … later …
        mgr.unbind("record")
        mgr.unbind_all()
    """

    def __init__(self) -> None:
        self._receiver = _HotkeyReceiver()
        # name → (hotkey_id, combo_string)
        self._bindings: dict[str, tuple[int, str]] = {}

    def bind(self, name: str, combo: str, callback: Callable[[], None]) -> None:
        """Bind (or rebind) a named hotkey to a combo string.

        Raises:
            ValueError   – combo string is invalid / unrecognised key name
            RuntimeError – RegisterHotKey failed (key taken by another app)
        """
        self.unbind(name)
        mods, vkey = _parse_combo(combo)
        id_ = self._receiver._do_register(mods, vkey, callback)
        self._bindings[name] = (id_, combo)

    def unbind(self, name: str) -> None:
        """Remove the named hotkey binding (no-op if not bound)."""
        entry = self._bindings.pop(name, None)
        if entry is not None:
            self._receiver._do_unregister(entry[0])

    def unbind_all(self) -> None:
        """Remove every registered hotkey."""
        self._receiver._unregister_all()
        self._bindings.clear()

    def current(self, name: str) -> Optional[str]:
        """Return the current combo string for a named hotkey, or None."""
        entry = self._bindings.get(name)
        return entry[1] if entry else None

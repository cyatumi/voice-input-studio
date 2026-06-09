"""Insert text into the currently focused window.

Default method: **direct Unicode injection** via Win32 SendInput with KEYEVENTF_UNICODE.
This types each character straight into the focused control without touching the
clipboard and without simulating Ctrl+V. Works in essentially every text input
on Windows — Word, Slack, Notion, browsers, IDEs, Office, Electron apps.

Fallback method: clipboard + Ctrl+V (kept for the rare case where direct
injection is blocked, e.g. some elevated/secure password fields).
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

import pyperclip


# --- Win32 SendInput plumbing ----------------------------------------------

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004

_VK_RETURN  = 0x0D
_VK_TAB     = 0x09
_VK_CONTROL = 0x11
_VK_V       = 0x56

_user32 = ctypes.WinDLL("user32", use_last_error=True)

# ULONG_PTR is the correct type for dwExtraInfo, but wintypes doesn't expose it
# directly across Python versions. Use ctypes.c_size_t which is the right width.
_ULONG_PTR = ctypes.c_size_t


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT


def _make_kb_input(vk: int, scan: int, flags: int) -> _INPUT:
    ki = _KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return _INPUT(type=_INPUT_KEYBOARD, u=_INPUT_UNION(ki=ki))


def _send_inputs(events: list[_INPUT]) -> None:
    if not events:
        return
    arr_type = _INPUT * len(events)
    arr = arr_type(*events)
    sent = _user32.SendInput(len(events), arr, ctypes.sizeof(_INPUT))
    if sent != len(events):
        # Most commonly this means UIPI blocked it (target window has higher integrity).
        err = ctypes.get_last_error()
        raise OSError(f"SendInput failed: sent {sent}/{len(events)} (error {err})")


def _events_for_char(ch: str) -> list[_INPUT]:
    """Build down+up events for a single character.

    Newlines/tabs go through real VK codes (so they trigger Enter/Tab behavior
    in textareas/forms). Everything else goes through KEYEVENTF_UNICODE,
    handling surrogate pairs for chars outside the BMP (some emoji).
    """
    if ch == "\n":
        return [
            _make_kb_input(_VK_RETURN, 0, 0),
            _make_kb_input(_VK_RETURN, 0, _KEYEVENTF_KEYUP),
        ]
    if ch == "\t":
        return [
            _make_kb_input(_VK_TAB, 0, 0),
            _make_kb_input(_VK_TAB, 0, _KEYEVENTF_KEYUP),
        ]
    if ch == "\r":
        return []  # ignore stray carriage returns

    events: list[_INPUT] = []
    # Iterate UTF-16 code units (2 bytes each, little-endian) so chars outside
    # the BMP get sent as a surrogate pair.
    encoded = ch.encode("utf-16-le")
    for i in range(0, len(encoded), 2):
        unit = int.from_bytes(encoded[i:i + 2], "little")
        events.append(_make_kb_input(0, unit, _KEYEVENTF_UNICODE))
        events.append(_make_kb_input(0, unit, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP))
    return events


def type_text(text: str, chunk_chars: int = 40, inter_chunk_delay: float = 0.005) -> None:
    """Type text directly into the focused window, character by character (Unicode-safe).

    Sends events in small chunks so that very long passages don't overwhelm the
    target app's input queue. Each chunk is a single SendInput call (fast).
    """
    if not text:
        return

    buffer: list[_INPUT] = []
    chars_in_buffer = 0
    for ch in text:
        buffer.extend(_events_for_char(ch))
        chars_in_buffer += 1
        if chars_in_buffer >= chunk_chars:
            _send_inputs(buffer)
            buffer.clear()
            chars_in_buffer = 0
            if inter_chunk_delay > 0:
                time.sleep(inter_chunk_delay)
    if buffer:
        _send_inputs(buffer)


# --- Fallback: clipboard + Ctrl+V ------------------------------------------

def paste_via_clipboard(text: str, restore_clipboard: bool = True) -> None:
    if not text:
        return
    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None

    pyperclip.copy(text)
    time.sleep(0.05)
    # Send Ctrl+V via SendInput — no keyboard-library dependency needed.
    _send_inputs([
        _make_kb_input(_VK_CONTROL, 0, 0),
        _make_kb_input(_VK_V,       0, 0),
        _make_kb_input(_VK_V,       0, _KEYEVENTF_KEYUP),
        _make_kb_input(_VK_CONTROL, 0, _KEYEVENTF_KEYUP),
    ])

    if restore_clipboard and previous is not None:
        time.sleep(0.3)
        try:
            pyperclip.copy(previous)
        except Exception:
            pass


def copy_only(text: str) -> None:
    """Don't insert — just put text on the clipboard."""
    if text:
        pyperclip.copy(text)


# --- Dispatcher -------------------------------------------------------------

def insert(text: str, method: str = "type") -> None:
    """Insert text using the configured method.

    method:
        "type"      — direct Unicode injection via SendInput (default, no clipboard touch)
        "paste"     — clipboard + Ctrl+V (fallback for rare incompatible apps)
        "clipboard" — copy to clipboard only, do not insert
    """
    if not text:
        return
    if method == "paste":
        paste_via_clipboard(text)
    elif method == "clipboard":
        copy_only(text)
    else:  # "type" or anything unknown → default to direct typing
        try:
            type_text(text)
        except OSError:
            # If SendInput is blocked (e.g. UIPI), fall back to clipboard paste
            # rather than silently swallowing the user's words.
            paste_via_clipboard(text)

"""Clipboard watcher + persistent history store.

Polls the system clipboard at ~2 Hz. Any new non-empty text snippet that
differs from the last entry is prepended to the history (capped, deduplicated).
History persists to %APPDATA%\\VoiceInputStudio\\data\\clipboard_history.json
so it survives restarts.

The watcher can be paused (used during our own clipboard-paste insertions so
we don't record what we just inserted).
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pyperclip

from . import config


@dataclass
class ClipboardEntry:
    text: str
    timestamp: str  # ISO format
    pinned: bool = False

    def preview(self, width: int = 80) -> str:
        single_line = self.text.replace("\n", " ⏎ ").replace("\r", "")
        if len(single_line) <= width:
            return single_line
        return single_line[: width - 1] + "…"


def _history_path() -> Path:
    return config.DATA_DIR / "clipboard_history.json"


def load_history() -> list[ClipboardEntry]:
    path = _history_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[ClipboardEntry] = []
    for item in raw:
        if isinstance(item, dict) and "text" in item:
            out.append(ClipboardEntry(
                text=item["text"],
                timestamp=item.get("timestamp", ""),
                pinned=bool(item.get("pinned", False)),
            ))
    return out


def save_history(entries: list[ClipboardEntry]) -> None:
    config.ensure_dirs()
    path = _history_path()
    serialized = [asdict(e) for e in entries]
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class ClipboardWatcher:
    """Background thread that polls the clipboard and notifies on changes."""

    def __init__(
        self,
        on_new_entry: Callable[[ClipboardEntry], None],
        poll_interval: float = 0.5,
        max_text_length: int = 100_000,
    ) -> None:
        self._on_new = on_new_entry
        self._poll = poll_interval
        self._max_len = max_text_length
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._paused = False
        self._last_seen: str | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            return
        # Seed with current clipboard so we don't re-record what was already there.
        try:
            self._last_seen = pyperclip.paste()
        except Exception:
            self._last_seen = ""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ClipboardWatcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def pause(self) -> None:
        """Temporarily stop recording (use during our own clipboard writes)."""
        self._paused = True

    def resume(self) -> None:
        # Re-baseline so we don't immediately record whatever's there now.
        try:
            self._last_seen = pyperclip.paste()
        except Exception:
            pass
        self._paused = False

    def _loop(self) -> None:
        while not self._stop_event.wait(self._poll):
            if self._paused:
                continue
            try:
                current = pyperclip.paste()
            except Exception:
                continue
            if not isinstance(current, str) or not current:
                continue
            if current == self._last_seen:
                continue
            self._last_seen = current
            if len(current) > self._max_len:
                continue  # Skip absurdly large blobs (probably file content, screenshots)
            entry = ClipboardEntry(text=current, timestamp=datetime.now().isoformat(timespec="seconds"))
            try:
                self._on_new(entry)
            except Exception:
                pass


class HistoryStore:
    """Thread-safe in-memory cache backed by clipboard_history.json."""

    def __init__(self, max_entries: int = 100) -> None:
        self._entries: list[ClipboardEntry] = load_history()
        self._max = max_entries
        self._lock = threading.Lock()

    def all(self) -> list[ClipboardEntry]:
        with self._lock:
            return list(self._entries)

    def add(self, entry: ClipboardEntry) -> None:
        with self._lock:
            # Deduplicate: if the exact text is already present, move it to top.
            self._entries = [e for e in self._entries if e.text != entry.text]
            self._entries.insert(0, entry)
            # Cap, but never drop pinned items.
            pinned = [e for e in self._entries if e.pinned]
            unpinned = [e for e in self._entries if not e.pinned]
            allowed_unpinned = max(0, self._max - len(pinned))
            self._entries = pinned + unpinned[:allowed_unpinned]
            save_history(self._entries)

    def remove(self, text: str) -> None:
        with self._lock:
            self._entries = [e for e in self._entries if e.text != text]
            save_history(self._entries)

    def clear(self, keep_pinned: bool = True) -> None:
        with self._lock:
            self._entries = [e for e in self._entries if e.pinned] if keep_pinned else []
            save_history(self._entries)

    def toggle_pin(self, text: str) -> None:
        with self._lock:
            for e in self._entries:
                if e.text == text:
                    e.pinned = not e.pinned
                    break
            save_history(self._entries)

    def set_max(self, n: int) -> None:
        with self._lock:
            self._max = max(1, n)

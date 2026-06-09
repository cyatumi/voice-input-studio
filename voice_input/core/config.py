"""Application paths and constants.

User data is stored in %APPDATA%\\VoiceInputStudio so that program updates
(which replace files in Program Files) never touch personal settings.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "VoiceInputStudio"


def _appdata_root() -> Path:
    """Return %APPDATA%\\VoiceInputStudio on Windows, ~/.config equivalent elsewhere."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / APP_NAME


APPDATA_DIR: Path = _appdata_root()
DATA_DIR: Path = APPDATA_DIR / "data"
BACKUP_DIR: Path = APPDATA_DIR / "backups"
LOG_DIR: Path = APPDATA_DIR / "logs"

SETTINGS_FILE = APPDATA_DIR / "settings.json"
TEMPLATES_FILE = DATA_DIR / "templates.json"
SNIPPETS_FILE = DATA_DIR / "snippets.json"
ADDRESSES_FILE = DATA_DIR / "addresses.json"
VOCABULARY_FILE = DATA_DIR / "vocabulary.json"
MODES_FILE = DATA_DIR / "modes.json"
HISTORY_FILE = LOG_DIR / "history.jsonl"


def ensure_dirs() -> None:
    """Create all required directories on first launch."""
    for d in (APPDATA_DIR, DATA_DIR, BACKUP_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def assets_dir() -> Path:
    """Bundled asset directory — works in both dev and PyInstaller frozen mode."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2] / "assets"

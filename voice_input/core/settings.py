"""Settings/data persistence with automatic backups.

Each data file is a self-contained JSON. Before any write, the previous version
is copied to backups/ so that the user can roll back accidental changes or
recover from a botched update.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config


DEFAULT_MODES = [
    {
        "name": "標準 (文脈整形・中)",
        "prompt": (
            "あなたは日本語の文字起こし整形アシスタントです。入力された音声認識テキストに対し、"
            "次のルールで整形してください: "
            "(1) 「えー」「あの」「えっと」などのフィラー語を削除、"
            "(2) 不自然な空白を除去、"
            "(3) 文脈から判断して句読点を適切に挿入、"
            "(4) 明らかな漢字の誤変換を文脈から修正、"
            "(5) 元の意味・口調・敬体/常体は絶対に変えない、"
            "(6) 余計な前置きや説明は出力せず、整形後のテキストのみ返す。"
        ),
        "is_default": True,
    },
    {
        "name": "ビジネスメール",
        "prompt": (
            "あなたはビジネスメール作成の専門家です。入力された音声メモを、"
            "取引先に送る丁寧なメール本文に書き直してください。件名提案は不要。"
            "本文のみ返してください。"
        ),
    },
    {
        "name": "箇条書きメモ",
        "prompt": (
            "入力された音声を、要点を抽出した簡潔な箇条書き(Markdown)に整理してください。"
            "ネクストアクションがあれば末尾に「## 次のアクション」として追記。"
        ),
    },
    {
        "name": "SNS/ブログ",
        "prompt": (
            "親しみやすい語り口で、読みやすいSNS投稿/ブログ風にリライトしてください。"
            "適度に改行を入れ、絵文字は最小限。"
        ),
    },
    {
        "name": "そのまま (整形なし)",
        "prompt": "",
    },
]


@dataclass
class Hotkey:
    """A single global hotkey binding, e.g. ctrl+shift+y."""

    modifiers: list[str] = field(default_factory=lambda: ["ctrl", "shift"])
    key: str = "y"

    def to_string(self) -> str:
        return "+".join([*self.modifiers, self.key])

    @classmethod
    def from_string(cls, s: str) -> "Hotkey":
        parts = [p.strip().lower() for p in s.split("+") if p.strip()]
        if not parts:
            return cls()
        return cls(modifiers=parts[:-1], key=parts[-1])


@dataclass
class AppSettings:
    # Hotkeys
    hotkey_record: str = "ctrl+shift+f9"
    hotkey_settings: str = "ctrl+shift+f10"
    hotkey_clipboard: str = "ctrl+shift+f8"

    # Clipboard history
    clipboard_history_enabled: bool = True
    clipboard_history_max: int = 100

    # AI providers
    openai_api_key: str = ""
    gemini_api_key: str = ""
    stt_model: str = "whisper-1"              # OpenAI Whisper API model
    refiner_provider: str = "gemini"          # "gemini" | "openai"
    refiner_model: str = "gemini-2.0-flash"   # model name when provider="gemini"
    refiner_openai_model: str = "gpt-4o-mini" # model name when provider="openai"
    refiner_mode_name: str = "標準 (文脈整形・中)"

    # Indicator
    indicator_enabled: bool = True
    indicator_position: str = "bottom-right"  # bottom-right | bottom-left | top-right | top-left | custom
    indicator_x: int = -1  # only used if position == "custom"
    indicator_y: int = -1
    character_style: str = "polygon"  # polygon | minimal | classic

    # Audio
    sample_rate: int = 16000  # Whisper expects 16kHz mono
    input_device_index: int = -1  # -1 = system default

    # Behavior
    # input_method:
    #   "type"      — 直接タイプ注入 (SendInput Unicode, クリップボードに触らない) ★推奨
    #   "paste"     — クリップボード経由 + Ctrl+V (互換性重視)
    #   "clipboard" — クリップボードにコピーのみ (貼付しない)
    input_method: str = "paste"
    auto_paste: bool = True       # Legacy; kept for backward compatibility with old configs
    play_sound_on_start: bool = True
    play_sound_on_stop: bool = True
    keep_history: bool = True
    history_max_entries: int = 500

    # Misc
    language: str = "ja"
    first_run_completed: bool = False


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (write-then-rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _backup_if_exists(path: Path) -> None:
    """Copy the existing file to backups/ before overwriting."""
    if not path.exists():
        return
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = config.BACKUP_DIR / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, dst)
    _prune_backups(path.stem, keep=10)


def _prune_backups(stem: str, keep: int = 10) -> None:
    """Keep only the N most recent backups for a given file stem."""
    candidates = sorted(
        config.BACKUP_DIR.glob(f"{stem}_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in candidates[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def load_settings() -> AppSettings:
    config.ensure_dirs()
    if not config.SETTINGS_FILE.exists():
        s = AppSettings()
        save_settings(s)
        return s
    try:
        data = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppSettings()
    defaults = asdict(AppSettings())
    defaults.update({k: v for k, v in data.items() if k in defaults})
    return AppSettings(**defaults)


def save_settings(s: AppSettings) -> None:
    config.ensure_dirs()
    _backup_if_exists(config.SETTINGS_FILE)
    _atomic_write(config.SETTINGS_FILE, json.dumps(asdict(s), ensure_ascii=False, indent=2))


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, value: Any) -> None:
    _backup_if_exists(path)
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2))


# --- Convenience accessors for each data file --------------------------------

def load_templates() -> dict[str, str]:
    return load_json(config.TEMPLATES_FILE, {})

def save_templates(d: dict[str, str]) -> None:
    save_json(config.TEMPLATES_FILE, d)

def load_snippets() -> list[dict]:
    return load_json(config.SNIPPETS_FILE, [])

def save_snippets(d: list[dict]) -> None:
    save_json(config.SNIPPETS_FILE, d)

def load_addresses() -> dict[str, dict]:
    return load_json(config.ADDRESSES_FILE, {})

def save_addresses(d: dict[str, dict]) -> None:
    save_json(config.ADDRESSES_FILE, d)

def load_vocabulary() -> dict[str, str]:
    return load_json(config.VOCABULARY_FILE, {})

def save_vocabulary(d: dict[str, str]) -> None:
    save_json(config.VOCABULARY_FILE, d)

def load_modes() -> list[dict]:
    modes = load_json(config.MODES_FILE, None)
    if modes is None:
        save_json(config.MODES_FILE, DEFAULT_MODES)
        return list(DEFAULT_MODES)
    return modes

def save_modes(d: list[dict]) -> None:
    save_json(config.MODES_FILE, d)


def export_all() -> dict:
    """Bundle everything into a single dict for backup/migration."""
    return {
        "_meta": {
            "app": config.APP_NAME,
            "exported_at": datetime.now().isoformat(),
            "format": 1,
        },
        "settings": asdict(load_settings()),
        "modes": load_modes(),
        "templates": load_templates(),
        "snippets": load_snippets(),
        "addresses": load_addresses(),
        "vocabulary": load_vocabulary(),
    }


def import_all(payload: dict) -> None:
    """Restore everything from an export_all() payload."""
    if "settings" in payload:
        s = AppSettings()
        for k, v in payload["settings"].items():
            if hasattr(s, k):
                setattr(s, k, v)
        save_settings(s)
    if "modes" in payload:
        save_modes(payload["modes"])
    if "templates" in payload:
        save_templates(payload["templates"])
    if "snippets" in payload:
        save_snippets(payload["snippets"])
    if "addresses" in payload:
        save_addresses(payload["addresses"])
    if "vocabulary" in payload:
        save_vocabulary(payload["vocabulary"])

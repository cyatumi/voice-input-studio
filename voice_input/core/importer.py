"""Import data from the legacy Chrome extension backup JSON."""
from __future__ import annotations

import json
from pathlib import Path

from . import settings as settings_mod


def import_from_chrome_extension(json_path: str | Path) -> dict[str, int]:
    """Read a Chrome-extension export and migrate it into the desktop app data store.

    Returns a dict with counts of imported items per category.
    """
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))

    if "sync" not in payload:
        raise ValueError("Chrome拡張のエクスポート形式ではありません (key 'sync' が見つかりません)")

    sync = payload["sync"] or {}
    counts: dict[str, int] = {}

    if "templates" in sync and isinstance(sync["templates"], dict):
        settings_mod.save_templates(sync["templates"])
        counts["templates"] = len(sync["templates"])

    if "snippets" in sync and isinstance(sync["snippets"], list):
        settings_mod.save_snippets(sync["snippets"])
        counts["snippets"] = len(sync["snippets"])

    if "addressInfo" in sync and isinstance(sync["addressInfo"], dict):
        settings_mod.save_addresses(sync["addressInfo"])
        counts["addresses"] = len(sync["addressInfo"])

    if "vocabulary" in sync and isinstance(sync["vocabulary"], dict):
        settings_mod.save_vocabulary(sync["vocabulary"])
        counts["vocabulary"] = len(sync["vocabulary"])

    if "customModes" in sync and isinstance(sync["customModes"], list):
        # Normalize Chrome ext shape ({name, prompt}) — already compatible.
        settings_mod.save_modes(sync["customModes"])
        counts["modes"] = len(sync["customModes"])

    if "apiSettings" in sync and isinstance(sync["apiSettings"], dict):
        # Pull Gemini key if present.
        api = sync["apiSettings"]
        s = settings_mod.load_settings()
        if api.get("provider") == "gemini" and api.get("apiKey"):
            s.gemini_api_key = api["apiKey"]
        if api.get("model"):
            s.refiner_model = api["model"]
        settings_mod.save_settings(s)
        counts["api_settings"] = 1

    return counts

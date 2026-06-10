"""Settings window — all options clickable from one place.

Tabs:
  1. 一般 (API keys, models, hotkeys, indicator position)
  2. モード (system prompts)
  3. 個人辞書 (vocabulary)
  4. テンプレート (auto-replace keywords)
  5. 定型文 (snippet popup)
  6. 住所 (address autofill)
  7. データ管理 (export / import / Chrome ext migration)
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QInputDialog, QKeySequenceEdit, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import __display_name__
from ..core import config, importer
from ..core import recorder as rec_mod
from ..core import settings as settings_mod
from ..core.settings import AppSettings


# --- Hotkey capture widget --------------------------------------------------

class HotkeyCapture(QLineEdit):
    """Click the field, press the desired combo, it captures it."""

    def __init__(self, initial: str = "") -> None:
        super().__init__(initial)
        self.setReadOnly(True)
        self.setPlaceholderText("クリックしてキーを押してください")

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        mods = []
        if event.modifiers() & Qt.ControlModifier:
            mods.append("ctrl")
        if event.modifiers() & Qt.ShiftModifier:
            mods.append("shift")
        if event.modifiers() & Qt.AltModifier:
            mods.append("alt")
        if event.modifiers() & Qt.MetaModifier:
            mods.append("win")
        key = event.key()
        # Ignore lone modifier presses
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return
        key_text = QKeySequence(key).toString().lower()
        if not key_text:
            return
        if not mods:
            # Refuse bare keys (would steal common typing keys system-wide)
            return
        combo = "+".join([*mods, key_text])
        self.setText(combo)


# --- Main settings window ---------------------------------------------------

class SettingsWindow(QDialog):
    """Tabbed settings dialog. All edits are saved immediately on apply."""

    settings_changed = Signal()  # emitted after a successful save

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__display_name__} — 設定")
        self.resize(820, 620)

        self._settings = settings_mod.load_settings()
        self._modes = settings_mod.load_modes()
        self._vocabulary = settings_mod.load_vocabulary()
        self._templates = settings_mod.load_templates()
        self._snippets = settings_mod.load_snippets()
        self._addresses = settings_mod.load_addresses()

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "一般")
        tabs.addTab(self._build_modes_tab(), "AIモード")
        tabs.addTab(self._build_vocab_tab(), "個人辞書")
        tabs.addTab(self._build_templates_tab(), "テンプレート")
        tabs.addTab(self._build_snippets_tab(), "定型文")
        tabs.addTab(self._build_addresses_tab(), "住所")
        tabs.addTab(self._build_data_tab(), "データ管理")

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        save_btn = QPushButton("保存して閉じる")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_all)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        bottom.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addLayout(bottom)

    # ----- General tab -----------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        # API keys
        api_box = QGroupBox("APIキー (両方とも必須)")
        api_form = QFormLayout(api_box)
        self._openai_key = QLineEdit(self._settings.openai_api_key)
        self._openai_key.setEchoMode(QLineEdit.Password)
        self._openai_key.setPlaceholderText("sk-...")
        self._gemini_key = QLineEdit(self._settings.gemini_api_key)
        self._gemini_key.setEchoMode(QLineEdit.Password)
        self._gemini_key.setPlaceholderText("AIza...")
        api_form.addRow("OpenAI API Key (Whisper STT):", self._openai_key)
        api_form.addRow("Google Gemini API Key (整形):", self._gemini_key)
        info = QLabel(
            "OpenAI: <a href='https://platform.openai.com/api-keys'>platform.openai.com/api-keys</a><br>"
            "Gemini: <a href='https://aistudio.google.com/app/apikey'>aistudio.google.com/app/apikey</a>"
        )
        info.setOpenExternalLinks(True)
        api_form.addRow("", info)
        v.addWidget(api_box)

        # Models
        models_box = QGroupBox("モデル")
        models_form = QFormLayout(models_box)
        self._stt_model = QLineEdit(self._settings.stt_model)
        models_form.addRow("Whisper モデル (STT):", self._stt_model)

        # Refiner provider selector
        self._refiner_provider = QComboBox()
        self._refiner_provider.addItem("Gemini (Google) ※無料枠あり", "gemini")
        self._refiner_provider.addItem("OpenAI GPT (OpenAI) ※Whisperと同じキー使用", "openai")
        idx = self._refiner_provider.findData(self._settings.refiner_provider)
        if idx >= 0:
            self._refiner_provider.setCurrentIndex(idx)
        models_form.addRow("整形エンジン:", self._refiner_provider)

        self._refiner_model = QLineEdit(self._settings.refiner_model)
        self._refiner_model.setPlaceholderText("gemini-2.0-flash")
        self._refiner_openai_model = QLineEdit(self._settings.refiner_openai_model)
        self._refiner_openai_model.setPlaceholderText("gpt-4o-mini")
        models_form.addRow("Gemini モデル:", self._refiner_model)
        models_form.addRow("OpenAI モデル:", self._refiner_openai_model)

        note = QLabel(
            "💡 Geminiの無料枠（429エラー）が上限に達したら<b>OpenAI GPT</b>に切り替えてください。<br>"
            "OpenAIはWhisperと同じAPIキーを使うため追加設定不要です。"
        )
        note.setWordWrap(True)
        models_form.addRow("", note)
        v.addWidget(models_box)

        # Hotkeys
        hot_box = QGroupBox("ショートカットキー (クリック→キーを押して登録)")
        hot_form = QFormLayout(hot_box)
        self._hk_record = HotkeyCapture(self._settings.hotkey_record)
        self._hk_settings = HotkeyCapture(self._settings.hotkey_settings)
        self._hk_clipboard = HotkeyCapture(self._settings.hotkey_clipboard)
        hot_form.addRow("録音 開始/停止:", self._hk_record)
        hot_form.addRow("設定画面を開く:", self._hk_settings)
        hot_form.addRow("クリップボード履歴を開く:", self._hk_clipboard)
        v.addWidget(hot_box)

        # Clipboard history
        clip_box = QGroupBox("クリップボード履歴")
        clip_form = QFormLayout(clip_box)
        self._clip_enabled = QCheckBox("クリップボード履歴を有効化 (バックグラウンドで監視)")
        self._clip_enabled.setChecked(self._settings.clipboard_history_enabled)
        clip_form.addRow("", self._clip_enabled)
        self._clip_max = QSpinBox()
        self._clip_max.setRange(10, 1000)
        self._clip_max.setValue(self._settings.clipboard_history_max)
        clip_form.addRow("保存する最大件数:", self._clip_max)
        v.addWidget(clip_box)

        # Indicator
        ind_box = QGroupBox("録音インジケーター")
        ind_form = QFormLayout(ind_box)
        self._ind_enabled = QCheckBox("録音中にダンシングキャラを表示")
        self._ind_enabled.setChecked(self._settings.indicator_enabled)
        self._ind_position = QComboBox()
        for label, value in [
            ("右下", "bottom-right"), ("左下", "bottom-left"),
            ("右上", "top-right"), ("左上", "top-left"),
            ("カスタム位置 (ドラッグで移動)", "custom"),
        ]:
            self._ind_position.addItem(label, value)
        idx = self._ind_position.findData(self._settings.indicator_position)
        if idx >= 0:
            self._ind_position.setCurrentIndex(idx)
        ind_form.addRow("", self._ind_enabled)
        ind_form.addRow("位置:", self._ind_position)
        v.addWidget(ind_box)

        # Audio
        audio_box = QGroupBox("音声入力デバイス")
        audio_form = QFormLayout(audio_box)
        self._device_combo = QComboBox()
        self._device_combo.addItem("システムの既定マイク", -1)
        try:
            for dev in rec_mod.list_input_devices():
                label = f"{dev['name']}" + (" (既定)" if dev["default"] else "")
                self._device_combo.addItem(label, dev["index"])
        except Exception:
            pass
        idx = self._device_combo.findData(self._settings.input_device_index)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)
        audio_form.addRow("マイク:", self._device_combo)
        v.addWidget(audio_box)

        # Behavior
        behave_box = QGroupBox("入力方式・動作")
        behave_form = QFormLayout(behave_box)
        self._input_method = QComboBox()
        for label, value in [
            ("直接タイプ注入 (推奨・クリップボードを使わない)", "type"),
            ("クリップボード経由 + Ctrl+V (互換性重視)", "paste"),
            ("クリップボードにコピーのみ (自分で貼付)", "clipboard"),
        ]:
            self._input_method.addItem(label, value)
        idx = self._input_method.findData(self._settings.input_method)
        if idx >= 0:
            self._input_method.setCurrentIndex(idx)
        behave_form.addRow("文字の入力方法:", self._input_method)
        self._keep_history = QCheckBox("入力履歴を保存する")
        self._keep_history.setChecked(self._settings.keep_history)
        behave_form.addRow("", self._keep_history)
        v.addWidget(behave_box)

        v.addStretch(1)
        return w

    # ----- Modes tab -------------------------------------------------------

    def _build_modes_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("整形に使うAIモード。「そのまま」は整形をスキップします。"))

        self._mode_active = QComboBox()
        self._refresh_mode_combo()
        v.addWidget(QLabel("現在使用中のモード:"))
        v.addWidget(self._mode_active)

        self._modes_table = QTableWidget(0, 2)
        self._modes_table.setHorizontalHeaderLabels(["モード名", "システムプロンプト"])
        self._modes_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._modes_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._refresh_modes_table()
        v.addWidget(self._modes_table, 1)

        btns = QHBoxLayout()
        add_btn = QPushButton("+ 追加")
        add_btn.clicked.connect(self._add_mode)
        del_btn = QPushButton("削除")
        del_btn.clicked.connect(self._delete_mode)
        btns.addStretch(1)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        v.addLayout(btns)
        return w

    def _refresh_mode_combo(self) -> None:
        self._mode_active.clear()
        for m in self._modes:
            self._mode_active.addItem(m["name"], m["name"])
        idx = self._mode_active.findData(self._settings.refiner_mode_name)
        if idx >= 0:
            self._mode_active.setCurrentIndex(idx)

    def _refresh_modes_table(self) -> None:
        self._modes_table.setRowCount(len(self._modes))
        for r, m in enumerate(self._modes):
            self._modes_table.setItem(r, 0, QTableWidgetItem(m.get("name", "")))
            self._modes_table.setItem(r, 1, QTableWidgetItem(m.get("prompt", "")))

    def _add_mode(self) -> None:
        name, ok = QInputDialog.getText(self, "モード追加", "モード名:")
        if not ok or not name:
            return
        prompt, ok = QInputDialog.getMultiLineText(
            self, "モード追加", "システムプロンプト:",
            "あなたは...",
        )
        if not ok:
            return
        self._modes.append({"name": name, "prompt": prompt})
        self._refresh_modes_table()
        self._refresh_mode_combo()

    def _delete_mode(self) -> None:
        row = self._modes_table.currentRow()
        if row < 0:
            return
        del self._modes[row]
        self._refresh_modes_table()
        self._refresh_mode_combo()

    # ----- Generic key/value tab helpers ------------------------------------

    def _build_kv_tab(
        self, title: str, key_label: str, val_label: str, kv_dict: dict,
        on_change: Callable[[dict], None],
    ) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(title))
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels([key_label, val_label])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        def refresh() -> None:
            table.setRowCount(len(kv_dict))
            for r, (k, val) in enumerate(kv_dict.items()):
                table.setItem(r, 0, QTableWidgetItem(k))
                table.setItem(r, 1, QTableWidgetItem(val))

        def commit() -> None:
            new = {}
            for r in range(table.rowCount()):
                k_item = table.item(r, 0)
                v_item = table.item(r, 1)
                k = (k_item.text().strip() if k_item else "")
                val = (v_item.text() if v_item else "")
                if k:
                    new[k] = val
            kv_dict.clear()
            kv_dict.update(new)
            on_change(kv_dict)

        # refresh() を先に呼んでから signal を接続する。逆順だと setItem() が
        # itemChanged を発火 → commit() が dict.clear() を呼び、イテレーション中に
        # dict サイズが変わって "dictionary changed size during iteration" になる。
        refresh()
        table.itemChanged.connect(lambda _: commit())
        v.addWidget(table, 1)

        btns = QHBoxLayout()
        add_btn = QPushButton("+ 追加")
        def add() -> None:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(""))
            table.setItem(row, 1, QTableWidgetItem(""))
        add_btn.clicked.connect(add)
        del_btn = QPushButton("削除")
        def remove() -> None:
            r = table.currentRow()
            if r >= 0:
                table.removeRow(r)
                commit()
        del_btn.clicked.connect(remove)
        btns.addStretch(1)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        v.addLayout(btns)
        return w

    def _build_vocab_tab(self) -> QWidget:
        return self._build_kv_tab(
            "音声認識の誤りを置換します。固有名詞や専門用語の登録に。",
            "誤 (認識される文字)", "正 (変換後)",
            self._vocabulary,
            lambda _: None,
        )

    def _build_templates_tab(self) -> QWidget:
        return self._build_kv_tab(
            "キーワードを発話すると、自動で文章に置き換わります。",
            "キーワード", "展開後の文章",
            self._templates,
            lambda _: None,
        )

    # ----- Snippets tab -----------------------------------------------------

    def _build_snippets_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("「定型文」と発話すると、ポップアップでこのリストから選択できます。"))
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["ラベル", "内容"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        def refresh() -> None:
            table.setRowCount(len(self._snippets))
            for r, s in enumerate(self._snippets):
                table.setItem(r, 0, QTableWidgetItem(s.get("label", "")))
                table.setItem(r, 1, QTableWidgetItem(s.get("content", "")))

        def commit() -> None:
            new = []
            for r in range(table.rowCount()):
                label = table.item(r, 0).text() if table.item(r, 0) else ""
                content = table.item(r, 1).text() if table.item(r, 1) else ""
                if label.strip():
                    new.append({"label": label, "content": content})
            self._snippets[:] = new

        # refresh() を先に呼んでから signal を接続する。逆順だと setItem() が
        # itemChanged を発火 → commit() が dict.clear() を呼び、イテレーション中に
        # dict サイズが変わって "dictionary changed size during iteration" になる。
        refresh()
        table.itemChanged.connect(lambda _: commit())
        v.addWidget(table, 1)

        btns = QHBoxLayout()
        add_btn = QPushButton("+ 追加")
        def add() -> None:
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(""))
            table.setItem(r, 1, QTableWidgetItem(""))
        add_btn.clicked.connect(add)
        del_btn = QPushButton("削除")
        def remove() -> None:
            r = table.currentRow()
            if r >= 0:
                table.removeRow(r)
                commit()
        del_btn.clicked.connect(remove)
        btns.addStretch(1)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        v.addLayout(btns)
        return w

    # ----- Addresses tab ----------------------------------------------------

    def _build_addresses_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("「住所自動入力」と発話するとポップアップが開き、選んだ住所がコピーされます。"))
        cols = ["キー", "名前", "フリガナ", "郵便番号", "都道府県", "市区町村", "番地・建物", "電話"]
        table = QTableWidget(0, len(cols))
        table.setHorizontalHeaderLabels(cols)
        for i in range(len(cols)):
            table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)

        def refresh() -> None:
            table.setRowCount(len(self._addresses))
            for r, (key, info) in enumerate(self._addresses.items()):
                vals = [key, info.get("name", ""), info.get("name_kana", ""),
                        info.get("zip", ""), info.get("pref", ""), info.get("city", ""),
                        info.get("street", ""), info.get("tel", "")]
                for c, val in enumerate(vals):
                    table.setItem(r, c, QTableWidgetItem(val))

        def commit() -> None:
            new: dict[str, dict] = {}
            for r in range(table.rowCount()):
                vals = [table.item(r, c).text() if table.item(r, c) else "" for c in range(len(cols))]
                key = vals[0].strip()
                if not key:
                    continue
                new[key] = {
                    "name": vals[1], "name_kana": vals[2], "zip": vals[3],
                    "pref": vals[4], "city": vals[5], "street": vals[6], "tel": vals[7],
                    "address": (vals[4] + vals[5] + vals[6]),
                }
            self._addresses.clear()
            self._addresses.update(new)

        # refresh() を先に呼んでから signal を接続する。逆順だと setItem() が
        # itemChanged を発火 → commit() が dict.clear() を呼び、イテレーション中に
        # dict サイズが変わって "dictionary changed size during iteration" になる。
        refresh()
        table.itemChanged.connect(lambda _: commit())
        v.addWidget(table, 1)

        btns = QHBoxLayout()
        add_btn = QPushButton("+ 追加")
        def add() -> None:
            r = table.rowCount()
            table.insertRow(r)
            for c in range(len(cols)):
                table.setItem(r, c, QTableWidgetItem(""))
        add_btn.clicked.connect(add)
        del_btn = QPushButton("削除")
        def remove() -> None:
            r = table.currentRow()
            if r >= 0:
                table.removeRow(r)
                commit()
        del_btn.clicked.connect(remove)
        btns.addStretch(1)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        v.addLayout(btns)
        return w

    # ----- Data tab ---------------------------------------------------------

    def _build_data_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        v.addWidget(QLabel(f"<b>データ保存場所:</b><br><code>{config.APPDATA_DIR}</code>"))
        v.addWidget(QLabel("プログラムを更新してもここのデータは消えません。"))

        v.addSpacing(10)
        v.addWidget(QLabel("<b>このアプリ全体をエクスポート/インポート</b>"))
        h = QHBoxLayout()
        export_btn = QPushButton("📥 全データをエクスポート")
        export_btn.clicked.connect(self._export_all)
        import_btn = QPushButton("📤 バックアップからインポート")
        import_btn.clicked.connect(self._import_all)
        h.addWidget(export_btn)
        h.addWidget(import_btn)
        h.addStretch(1)
        v.addLayout(h)

        v.addSpacing(20)
        v.addWidget(QLabel("<b>旧Chrome拡張機能からデータ移行</b>"))
        v.addWidget(QLabel("拡張機能の「データ管理」でエクスポートしたJSONを選択してください。"))
        chrome_btn = QPushButton("🔄 Chrome拡張データを取り込む")
        chrome_btn.clicked.connect(self._import_chrome)
        v.addWidget(chrome_btn)

        v.addSpacing(20)
        v.addWidget(QLabel("<b>バックアップフォルダ</b>"))
        backup_btn = QPushButton("📂 バックアップフォルダを開く")
        backup_btn.clicked.connect(self._open_backups)
        v.addWidget(backup_btn)

        v.addStretch(1)
        return w

    def _export_all(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "全データをエクスポート",
            f"voice-input-studio-backup_{datetime.now():%Y%m%d_%H%M%S}.json",
            "JSON (*.json)",
        )
        if not path:
            return
        payload = settings_mod.export_all()
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        QMessageBox.information(self, "エクスポート完了", f"保存しました:\n{path}")

    def _import_all(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "バックアップを選択", "", "JSON (*.json)")
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            settings_mod.import_all(payload)
            QMessageBox.information(self, "インポート完了",
                                    "復元しました。設定画面を開き直してください。")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "失敗", str(e))

    def _import_chrome(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chrome拡張のエクスポートJSONを選択", "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            counts = importer.import_from_chrome_extension(path)
            msg = "取り込み完了:\n" + "\n".join(f"  {k}: {v}件" for k, v in counts.items())
            QMessageBox.information(self, "インポート完了", msg + "\n\n設定画面を開き直してください。")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "失敗", str(e))

    def _open_backups(self) -> None:
        import os
        import subprocess
        config.ensure_dirs()
        os.startfile(str(config.BACKUP_DIR))  # type: ignore[attr-defined]

    # ----- Save -------------------------------------------------------------

    def _save_all(self) -> None:
        s = self._settings
        s.openai_api_key = self._openai_key.text().strip()
        s.gemini_api_key = self._gemini_key.text().strip()
        s.stt_model = self._stt_model.text().strip() or "whisper-1"
        s.refiner_provider = self._refiner_provider.currentData() or "gemini"
        s.refiner_model = self._refiner_model.text().strip() or "gemini-2.0-flash"
        s.refiner_openai_model = self._refiner_openai_model.text().strip() or "gpt-4o-mini"

        if self._hk_record.text():
            s.hotkey_record = self._hk_record.text()
        if self._hk_settings.text():
            s.hotkey_settings = self._hk_settings.text()
        if self._hk_clipboard.text():
            s.hotkey_clipboard = self._hk_clipboard.text()
        s.clipboard_history_enabled = self._clip_enabled.isChecked()
        s.clipboard_history_max = self._clip_max.value()

        s.indicator_enabled = self._ind_enabled.isChecked()
        s.indicator_position = self._ind_position.currentData()
        s.input_device_index = self._device_combo.currentData()
        s.input_method = self._input_method.currentData() or "type"
        s.keep_history = self._keep_history.isChecked()
        s.refiner_mode_name = self._mode_active.currentData() or s.refiner_mode_name
        s.first_run_completed = True

        settings_mod.save_settings(s)
        settings_mod.save_modes(self._modes)
        settings_mod.save_vocabulary(self._vocabulary)
        settings_mod.save_templates(self._templates)
        settings_mod.save_snippets(self._snippets)
        settings_mod.save_addresses(self._addresses)

        self.settings_changed.emit()
        self.accept()

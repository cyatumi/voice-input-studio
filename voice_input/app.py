"""Top-level application controller — wires everything together."""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox

from .core import config
from .core import settings as settings_mod
from .core import updater
from .core.clipboard_history import ClipboardEntry, ClipboardWatcher, HistoryStore
from .core.hotkey import HotkeyManager
from .core.inserter import insert as inserter_dispatch, copy_only as inserter_copy
from .core.recorder import Recorder
from .core.refiner import GeminiRefiner, OpenAIRefiner
from .core.stt import WhisperSTT
from .ui.clipboard_popup import ClipboardHistoryPopup
from .ui.indicator import IndicatorWindow
from .ui.settings_window import SettingsWindow
from .ui.tray import TrayController


SNIPPET_TRIGGER = "定型文"
ADDRESS_TRIGGER = "住所自動入力"


class AppController(QObject):
    """Orchestrates the full record → transcribe → refine → paste pipeline."""

    level_changed = Signal(float)
    pipeline_finished = Signal(str)  # final inserted text

    # Thread-safe triggers — emitted from keyboard-library thread OR background
    # pipeline thread; Qt delivers them to the main thread via queued connection.
    # NOTE: QTimer.singleShot() does NOT work from plain threading.Thread because
    # that thread has no Qt event loop.  Signals do work — always use signals for
    # anything that needs to run on the Qt main thread from a background thread.
    _sig_record    = Signal()
    _sig_settings  = Signal()
    _sig_clipboard = Signal()
    _sig_insert    = Signal(str)       # (text)         → _insert_final
    _sig_notify    = Signal(str, str)  # (title, body)  → tray.notify
    _sig_snippet   = Signal()          #                → _handle_snippet_trigger
    _sig_address   = Signal()          #                → _handle_address_trigger
    _sig_proc_end  = Signal()          #                → _end_processing (hide 翻訳中)

    # Auto-update signals (emitted from the background update-check / download
    # threads; delivered to the Qt main thread so dialogs are created safely).
    _sig_update_found    = Signal(object)    # (UpdateInfo) → _on_update_found
    _sig_update_none     = Signal()          #              → "最新です" notice
    _sig_update_error    = Signal(str)       # (message)    → check-failed notice
    _sig_update_progress = Signal(int, int)  # (read, total)→ progress dialog
    _sig_update_ready    = Signal(str)       # (exe path)   → apply + restart
    _sig_update_dlfail   = Signal(str)       # (message)    → download-failed

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.settings = settings_mod.load_settings()

        self.recorder: Recorder | None = None
        self.stt = WhisperSTT(self.settings.openai_api_key, self.settings.stt_model)
        self.refiner = self._make_refiner(self.settings)

        self.indicator = IndicatorWindow()
        self.indicator.stop_requested.connect(self.toggle_recording)
        self.level_changed.connect(self.indicator.set_level)

        self.tray = TrayController(
            on_toggle_record=self.toggle_recording,
            on_open_settings=self.open_settings,
            on_quit=self.quit,
            on_open_data_folder=self._open_data_folder,
            on_open_clipboard=self.open_clipboard_history,
            on_check_update=self.check_update_manual,
        )

        # Clipboard history
        self.clipboard_store = HistoryStore(max_entries=self.settings.clipboard_history_max)
        self.clipboard_watcher = ClipboardWatcher(on_new_entry=self._on_clipboard_change)
        if self.settings.clipboard_history_enabled:
            self.clipboard_watcher.start()

        # Wire all signals → slots (main-thread delivery guaranteed for every
        # signal, whether emitted from the hotkey thread or pipeline thread).
        self._sig_record.connect(self.toggle_recording)
        self._sig_settings.connect(self.open_settings)
        self._sig_clipboard.connect(self.open_clipboard_history)
        self._sig_insert.connect(self._insert_final)
        self._sig_notify.connect(self._on_notify)
        self._sig_snippet.connect(self._handle_snippet_trigger)
        self._sig_address.connect(self._handle_address_trigger)
        self._sig_proc_end.connect(self._end_processing)

        # Auto-update wiring
        self._update_dlg = None            # active QProgressDialog, if any
        self._sig_update_found.connect(self._on_update_found)
        self._sig_update_none.connect(self._on_update_none)
        self._sig_update_error.connect(self._on_update_error)
        self._sig_update_progress.connect(self._on_update_progress)
        self._sig_update_ready.connect(self._on_update_downloaded)
        self._sig_update_dlfail.connect(self._on_update_dlfail)

        self.hotkeys = HotkeyManager()
        self._rebind_hotkeys()

        # Level polling timer — reads recorder._current_level on the Qt main thread
        # every 33 ms (~30 fps) and updates the indicator.  This avoids relying on
        # Signal.emit() from PortAudio's native C thread, which can silently fail.
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(33)
        self._level_timer.timeout.connect(self._poll_level)

        # State for the active pipeline
        self._busy = False
        self._insert_target_hwnd: int = 0   # foreground window captured at recording-stop
        self._settings_window: SettingsWindow | None = None
        self._clipboard_popup: ClipboardHistoryPopup | None = None

        # Startup notification — always show so the user knows the tray icon is ready.
        if self.settings.first_run_completed:
            QTimer.singleShot(1000, lambda: self.tray.notify(
                "Voice Input Studio が起動しました",
                f"録音: {self.settings.hotkey_record}  |  設定: {self.settings.hotkey_settings}",
            ))
        else:
            QTimer.singleShot(800, self._first_run_prompt)

        # Check for a new version a few seconds after startup, in the
        # background.  Silent: only speaks up if an update is actually found.
        QTimer.singleShot(5000, self._check_update_silent)

    # --- Auto-update --------------------------------------------------------

    def _check_update_silent(self) -> None:
        """Background update check on startup — no UI unless an update exists."""
        threading.Thread(target=self._run_update_check, args=(False,), daemon=True).start()

    @Slot()
    def check_update_manual(self) -> None:
        """Tray menu '更新を確認' — always reports the result either way."""
        self.tray.notify("更新の確認", "最新バージョンを確認しています...")
        threading.Thread(target=self._run_update_check, args=(True,), daemon=True).start()

    def _run_update_check(self, verbose: bool) -> None:
        try:
            info = updater.check_for_update()
        except Exception as e:  # defensive — check_for_update already swallows
            if verbose:
                self._sig_update_error.emit(str(e))
            return
        if info is not None:
            self._sig_update_found.emit(info)
        elif verbose:
            self._sig_update_none.emit()

    @Slot()
    def _on_update_none(self) -> None:
        self.tray.notify("更新の確認", f"お使いの v{updater.CURRENT_VERSION} が最新です。")

    @Slot(str)
    def _on_update_error(self, message: str) -> None:
        self.tray.notify("更新の確認に失敗", message[:120])

    @Slot(object)
    def _on_update_found(self, info) -> None:
        msg = (
            f"新しいバージョン v{info.version} が公開されています。\n"
            f"（現在: v{updater.CURRENT_VERSION}）\n\n更新しますか？"
        )
        if info.notes:
            msg += f"\n\n― 変更点 ―\n{info.notes}"
        ans = QMessageBox.question(
            None, "アップデート", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        if not updater.is_frozen():
            QMessageBox.information(
                None, "アップデート",
                "開発モードで実行中のため自動更新はできません。\n"
                "配布版 (VoiceInputStudio.exe) で実行してください。",
            )
            return
        if not updater.can_write_target():
            QMessageBox.warning(
                None, "アップデートできません",
                "アプリのフォルダに書き込めません。\n\n"
                "デスクトップやドキュメントなど、書き込み可能な場所に\n"
                "アプリのフォルダを移動してから、もう一度お試しください。",
            )
            return
        self._start_download(info)

    def _start_download(self, info) -> None:
        from PySide6.QtWidgets import QProgressDialog
        dlg = QProgressDialog("新しいバージョンをダウンロードしています...", None, 0, 100, None)
        dlg.setWindowTitle("アップデート")
        dlg.setCancelButton(None)        # download must finish to apply safely
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        dlg.show()
        self._update_dlg = dlg
        threading.Thread(target=self._download_worker, args=(info,), daemon=True).start()

    def _download_worker(self, info) -> None:
        try:
            path = updater.download_exe(
                info.url,
                lambda read, total: self._sig_update_progress.emit(read, total),
            )
        except Exception as e:
            self._sig_update_dlfail.emit(str(e))
            return
        self._sig_update_ready.emit(str(path))

    @Slot(int, int)
    def _on_update_progress(self, read: int, total: int) -> None:
        if self._update_dlg is None:
            return
        mb = 1024 * 1024
        if total > 0:
            self._update_dlg.setValue(int(read * 100 / total))
            self._update_dlg.setLabelText(
                f"ダウンロード中... {read // mb} MB / {total // mb} MB"
            )
        else:
            self._update_dlg.setLabelText(f"ダウンロード中... {read // mb} MB")

    @Slot(str)
    def _on_update_downloaded(self, path: str) -> None:
        if self._update_dlg is not None:
            self._update_dlg.close()
            self._update_dlg = None
        QMessageBox.information(
            None, "アップデート",
            "ダウンロードが完了しました。\n"
            "「OK」を押すとアプリを再起動して更新を適用します。",
        )
        try:
            updater.apply_update_and_restart(Path(path))
        except Exception as e:
            QMessageBox.critical(None, "アップデート失敗", str(e))
            return
        self.quit()

    @Slot(str)
    def _on_update_dlfail(self, message: str) -> None:
        if self._update_dlg is not None:
            self._update_dlg.close()
            self._update_dlg = None
        QMessageBox.critical(
            None, "ダウンロード失敗",
            f"更新のダウンロードに失敗しました。\n\n{message[:200]}",
        )

    # --- Hotkey management ---------------------------------------------------

    def _rebind_hotkeys(self) -> None:
        self.hotkeys.unbind_all()
        try:
            # Use Signal.emit() — thread-safe: keyboard callback runs on a
            # background thread; Signal delivers it to the Qt main thread.
            self.hotkeys.bind("record_toggle", self.settings.hotkey_record,
                              self._sig_record.emit)
        except Exception as e:
            self.tray.notify("ホットキー登録失敗", str(e))
        try:
            self.hotkeys.bind("open_settings", self.settings.hotkey_settings,
                              self._sig_settings.emit)
        except Exception:
            pass
        if self.settings.clipboard_history_enabled and self.settings.hotkey_clipboard:
            try:
                self.hotkeys.bind("open_clipboard", self.settings.hotkey_clipboard,
                                  self._sig_clipboard.emit)
            except Exception as e:
                self.tray.notify("クリップボード履歴ホットキー登録失敗", str(e))

    # --- Recording lifecycle ------------------------------------------------

    @Slot()
    def toggle_recording(self) -> None:
        if self._busy:
            return
        if self.recorder and self.recorder.is_recording:
            self._stop_and_process()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if not self.settings.openai_api_key:
            self.tray.notify("APIキー未設定", "設定画面でOpenAI APIキーを入力してください。")
            self.open_settings()
            return
        try:
            self.recorder = Recorder(
                sample_rate=self.settings.sample_rate,
                channels=1,
                device=self.settings.input_device_index,
            )
            self.recorder.start()
        except Exception as e:
            self.tray.notify("録音失敗", str(e))
            return

        self._level_timer.start()   # begin polling recorder._current_level
        self.tray.set_recording(True)
        if self.settings.indicator_enabled:
            self.indicator.show_at(
                self.settings.indicator_position,
                self.settings.indicator_x, self.settings.indicator_y,
            )

    def _stop_and_process(self) -> None:
        assert self.recorder is not None

        # Capture which window the user was working in BEFORE anything changes.
        # We restore focus to it just before inserting text, so the 2-5 s STT
        # delay doesn't accidentally reroute keystrokes to the wrong window.
        try:
            import ctypes
            self._insert_target_hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            self._insert_target_hwnd = 0

        self._level_timer.stop()
        self.level_changed.emit(0.0)    # reset indicator to idle
        wav = self.recorder.stop()
        self.recorder = None
        self.tray.set_recording(False)
        # Keep the indicator on screen in a "翻訳中" state while the cloud STT
        # (and optional refine) runs, so the user has clear feedback that the
        # app is working. It is dismissed when text is inserted (_do_insert) or
        # on any error / early-return path (_sig_proc_end → _end_processing).
        if self.settings.indicator_enabled:
            self.indicator.set_processing(True)
        else:
            self.indicator.hide()

        if not wav:
            self.indicator.set_processing(False)
            self.indicator.hide()
            self.tray.notify("録音データなし", "マイクが正しく選択されているか設定で確認してください。")
            return

        self._busy = True
        # Run the heavy network calls in a background thread so the UI stays alive.
        threading.Thread(target=self._pipeline, args=(wav,), daemon=True).start()

    def _pipeline(self, wav_bytes: bytes) -> None:
        try:
            raw = self.stt.transcribe(wav_bytes, language=self.settings.language)
        except Exception as e:
            # Use signal — QTimer.singleShot() silently does nothing from a
            # plain threading.Thread (no Qt event loop in that thread).
            self._sig_notify.emit("文字起こし失敗", str(e))
            self._sig_proc_end.emit()
            self._busy = False
            return

        # Strip Whisper-inserted whitespace (the old extension did this too).
        text = (raw or "").replace(" ", "").strip()
        if not text:
            self._sig_notify.emit(
                "音声を認識できませんでした",
                "もう少しはっきり・長めに話してみてください。",
            )
            self._sig_proc_end.emit()
            self._busy = False
            return

        # Voice command triggers — handled on the GUI thread via signals.
        if SNIPPET_TRIGGER in text:
            self._sig_snippet.emit()
            self._sig_proc_end.emit()
            self._busy = False
            return
        if ADDRESS_TRIGGER in text:
            self._sig_address.emit()
            self._sig_proc_end.emit()
            self._busy = False
            return

        # Address keyword check (auto-fire if user spoke a registered key).
        addresses = settings_mod.load_addresses()
        for key, info in addresses.items():
            if key in text:
                full = info.get("address") or (info.get("pref", "") + info.get("city", "") + info.get("street", ""))
                if full:
                    self._sig_insert.emit(full)
                    self._busy = False
                    return

        # Template expansion
        templates = settings_mod.load_templates()
        for k, v in templates.items():
            if k in text:
                text = text.replace(k, v)

        # Find active mode prompt
        active_mode_name = self.settings.refiner_mode_name
        modes = settings_mod.load_modes()
        active_mode = next((m for m in modes if m.get("name") == active_mode_name), None)
        prompt = active_mode.get("prompt", "") if active_mode else ""

        vocabulary = settings_mod.load_vocabulary()

        if self.settings.gemini_api_key and prompt:
            try:
                final = self.refiner.refine(text, prompt, vocabulary)
            except Exception as e:
                self._sig_notify.emit("整形失敗 (生テキストを使用)", str(e))
                final = text
        else:
            # No refinement; still apply vocabulary as a hard rewrite.
            final = text
            for w, r in vocabulary.items():
                final = final.replace(w, r)

        self._log_history(raw, final)
        self._sig_insert.emit(final)  # crosses thread boundary safely via signal
        self._busy = False

    @Slot(str, str)
    def _on_notify(self, title: str, message: str) -> None:
        """Relay for _sig_notify — ensures tray.notify() is called on the main thread."""
        self.tray.notify(title, message)

    @Slot()
    def _end_processing(self) -> None:
        """Dismiss the 翻訳中 indicator on pipeline paths that don't insert text."""
        self.indicator.set_processing(False)
        self.indicator.hide()

    @Slot()
    def _poll_level(self) -> None:
        """Read recorder's latest audio level and push to indicator (main thread)."""
        if self.recorder and self.recorder.is_recording:
            self.level_changed.emit(self.recorder._current_level)

    def _insert_final(self, text: str) -> None:
        """Restore focus to the recording-time window, then schedule insertion.

        We use QTimer instead of time.sleep so the Qt event loop stays alive
        while the target window activates.  SwitchToThisWindow bypasses the
        Windows foreground-lock that blocks SetForegroundWindow from non-
        foreground processes.
        """
        if self._insert_target_hwnd:
            try:
                import ctypes
                hwnd = self._insert_target_hwnd
                # SW_RESTORE (9) also un-maximizes a maximized window — only
                # call it when the window is actually minimized (iconic).
                if ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass

        # Give the window ~300 ms to fully activate before we type into it.
        QTimer.singleShot(300, lambda: self._do_insert(text))

    def _do_insert(self, text: str) -> None:
        """Perform the actual text insertion (runs on Qt main thread)."""
        # Default to "paste" (clipboard + Ctrl+V) which works reliably on
        # Japanese Windows regardless of IME state or UIPI restrictions.
        method = self.settings.input_method or "paste"
        # Suppress clipboard recording during our own insertion in "paste" mode.
        if method == "paste":
            self.clipboard_watcher.pause()
        try:
            inserter_dispatch(text, method=method)
        except Exception as e:
            self.tray.notify("テキスト入力失敗", str(e))
        finally:
            if method == "paste":
                QTimer.singleShot(500, self.clipboard_watcher.resume)
        # 安全網: 貼り付け先が選ばれていなくても文字を失わないよう、文字起こし結果を
        # 必ずクリップボードと履歴にも残す（Ctrl+V / 履歴ポップアップで復旧できる）。
        # method=="clipboard" は既にコピー済みなので二重処理しない。
        if method != "clipboard" and getattr(self.settings, "always_copy_to_clipboard", True):
            self._stash_to_clipboard(text)
        if method == "clipboard":
            self.tray.notify("クリップボードにコピー", text[:60])
        # Translation finished and text inserted — dismiss the 翻訳中 indicator.
        self.indicator.set_processing(False)
        self.indicator.hide()
        # "入力完了" 通知は省略 — Windows トースト通知がブラウザ通知と
        # 混同されやすいため。エラー時のみ通知する。
        self.pipeline_finished.emit(text)

    def _stash_to_clipboard(self, text: str) -> None:
        """文字起こし結果をクリップボードと履歴に保存し、いつでも復旧できるようにする。"""
        if not text:
            return
        try:
            inserter_copy(text)  # クリップボードへコピー（貼付はしない）
        except Exception:
            pass
        try:
            self.clipboard_store.add(
                ClipboardEntry(text=text, timestamp=datetime.now().isoformat())
            )
        except Exception:
            pass

    # --- Clipboard history --------------------------------------------------

    def _on_clipboard_change(self, entry: ClipboardEntry) -> None:
        self.clipboard_store.add(entry)

    @Slot()
    def open_clipboard_history(self, initial_tab: int = 0) -> None:
        if not self.settings.clipboard_history_enabled and initial_tab == ClipboardHistoryPopup.TAB_CLIPBOARD:
            self.tray.notify("クリップボード履歴は無効です", "設定画面から有効化できます。")
            return
        if self._clipboard_popup is not None:
            try:
                if self._clipboard_popup.isVisible():
                    # Already open: just switch to the requested tab and focus.
                    self._clipboard_popup._tabs.setCurrentIndex(initial_tab)
                    self._clipboard_popup.raise_()
                    self._clipboard_popup.activateWindow()
                    return
            except RuntimeError:
                self._clipboard_popup = None
        self._clipboard_popup = ClipboardHistoryPopup(
            store=self.clipboard_store,
            on_pick=self._paste_from_clipboard_history,
            snippets=settings_mod.load_snippets(),
            addresses=settings_mod.load_addresses(),
            initial_tab=initial_tab,
        )
        self._clipboard_popup.show()
        self._clipboard_popup.raise_()
        self._clipboard_popup.activateWindow()

    def _paste_from_clipboard_history(self, text: str) -> None:
        # Insert the picked text EXACTLY as stored, via clipboard + Ctrl+V.
        #
        # We deliberately do NOT use method="type" (direct SendInput Unicode
        # injection): for long, multi-line Japanese passages — exactly what
        # snippets are — fast character-by-character injection races the target
        # app's IME/input queue and drops or reorders characters, producing
        # garbled output. Clipboard paste delivers the text atomically and
        # verbatim. Pause the clipboard watcher around our own paste so it
        # doesn't record the snippet as a new clipboard-history entry.
        self.clipboard_watcher.pause()
        try:
            inserter_dispatch(text, method="paste")
        except Exception as e:
            self.tray.notify("貼り付け失敗", str(e))
        finally:
            QTimer.singleShot(500, self.clipboard_watcher.resume)

    def _log_history(self, raw: str, final: str) -> None:
        if not self.settings.keep_history:
            return
        try:
            config.ensure_dirs()
            entry = {
                "ts": datetime.now().isoformat(),
                "mode": self.settings.refiner_mode_name,
                "raw": raw,
                "final": final,
            }
            with config.HISTORY_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # --- Voice command handlers ---------------------------------------------

    def _handle_snippet_trigger(self) -> None:
        """Voice command '定型文' → open popup with snippets tab active."""
        self.open_clipboard_history(initial_tab=ClipboardHistoryPopup.TAB_SNIPPETS)

    def _handle_address_trigger(self) -> None:
        """Voice command '住所自動入力' → open popup with addresses tab active."""
        self.open_clipboard_history(initial_tab=ClipboardHistoryPopup.TAB_ADDRESSES)

    # --- Settings / misc ---------------------------------------------------

    @Slot()
    def open_settings(self) -> None:
        # Guard against stale Qt C++ object (e.g. WA_DeleteOnClose already fired).
        if self._settings_window is not None:
            try:
                if self._settings_window.isVisible():
                    self._force_settings_front()
                    return
            except RuntimeError:
                self._settings_window = None

        # Always create a fresh window so it loads the latest saved settings.
        # Wrap in try/except — --noconsole builds silently swallow exceptions
        # from slots, so without this the user sees nothing when init fails.
        try:
            self._settings_window = SettingsWindow()
        except Exception as e:
            self.tray.notify("設定画面を開けませんでした", str(e)[:120])
            return

        self._settings_window.settings_changed.connect(self._on_settings_changed)

        # Position at screen centre before showing so it never appears off-screen.
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen().availableGeometry()
        w, h = 820, 640
        self._settings_window.setGeometry(
            screen.x() + (screen.width()  - w) // 2,
            screen.y() + (screen.height() - h) // 2,
            w, h,
        )

        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()
        QTimer.singleShot(150, self._force_settings_front)

    def _force_settings_front(self) -> None:
        """Bring the settings window to the foreground using Win32 API."""
        if self._settings_window is None:
            return
        try:
            self._settings_window.raise_()
            self._settings_window.activateWindow()
            import ctypes
            hwnd = int(self._settings_window.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 5)      # SW_SHOW (not SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    @staticmethod
    def _make_refiner(s) -> GeminiRefiner | OpenAIRefiner:
        if s.refiner_provider == "openai":
            return OpenAIRefiner(s.openai_api_key, s.refiner_openai_model or "gpt-4o-mini")
        return GeminiRefiner(s.gemini_api_key, s.refiner_model or "gemini-2.0-flash")

    def _on_settings_changed(self) -> None:
        self.settings = settings_mod.load_settings()
        # Re-create dependent objects so new keys / provider take effect.
        self.stt = WhisperSTT(self.settings.openai_api_key, self.settings.stt_model)
        self.refiner = self._make_refiner(self.settings)
        self.clipboard_store.set_max(self.settings.clipboard_history_max)
        if self.settings.clipboard_history_enabled and not self.clipboard_watcher.is_running:
            self.clipboard_watcher.start()
        elif not self.settings.clipboard_history_enabled and self.clipboard_watcher.is_running:
            self.clipboard_watcher.stop()
        self._rebind_hotkeys()

    def _open_data_folder(self) -> None:
        config.ensure_dirs()
        try:
            os.startfile(str(config.APPDATA_DIR))  # type: ignore[attr-defined]
        except OSError:
            pass

    def _first_run_prompt(self) -> None:
        QMessageBox.information(
            None,
            "Voice Input Studio へようこそ",
            "右下のタスクトレイにマイクアイコンが表示されました。\n\n"
            "1. アイコンを右クリック → 「設定を開く」\n"
            "2. OpenAI と Gemini の API キーを入力\n"
            "3. ホットキー (デフォルト: Ctrl+Shift+Y) で録音開始/停止\n\n"
            "旧Chrome拡張機能のデータは、設定 → データ管理 から取り込めます。",
        )
        QTimer.singleShot(100, self.open_settings)

    def quit(self) -> None:
        self.hotkeys.unbind_all()
        self.clipboard_watcher.stop()
        self.app.quit()

"""Entry point: `python -m voice_input` or invoked directly by the packaged exe.

Uses absolute imports so the same module works both as `python -m voice_input`
(where Python sets __package__) and as a frozen PyInstaller --onefile exe
(where __main__.py runs standalone with no parent package).
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from voice_input.app import AppController


def _already_running() -> bool:
    """Return True if another VoiceInputStudio process is already running.

    Uses a Windows named mutex so even --onefile PyInstaller exes that
    spawn an inner helper process are handled correctly.
    """
    try:
        import ctypes
        handle = ctypes.windll.kernel32.CreateMutexW(None, True, "VoiceInputStudio_SingleInstance")
        # ERROR_ALREADY_EXISTS == 183
        return ctypes.windll.kernel32.GetLastError() == 183
    except Exception:
        return False  # Can't check → allow startup


def main() -> int:
    if _already_running():
        _app = QApplication(sys.argv)
        QMessageBox.information(
            None,
            "Voice Input Studio",
            "Voice Input Studio はすでに起動しています。\n\n"
            "タスクバー右下の ^ をクリックしてマイクアイコンを探してください。",
        )
        return 0

    # High-DPI awareness so the indicator looks crisp on 4K monitors.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray app — closing settings shouldn't kill us

    controller = AppController(app)  # noqa: F841  (kept alive via the QApplication)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

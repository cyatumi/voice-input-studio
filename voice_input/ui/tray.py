"""System-tray icon with context menu.

On Windows 11, custom frameless QWidget popups are unreliable:
  - Qt.WindowType.Popup intercepts button clicks (they never reach signals).
  - Qt.WindowType.Tool / Window: DWM forces a transparent backdrop regardless
    of what the widget paints, on Windows 11 with certain compositor settings.

Solution: QMenu.exec() — Qt's built-in menu system has its own opaque
rendering that is immune to DWM backdrop effects, and exec() runs a local
event loop so selection is rock-solid on all Windows versions.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from voice_input import __display_name__, __version__


# ---------------------------------------------------------------------------
# Tray icon painter
# ---------------------------------------------------------------------------

def _make_icon(color: QColor, dot: bool = False) -> QIcon:
    pix = QPixmap(QSize(32, 32))
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(color)
    p.setPen(QColor(255, 255, 255, 200))
    p.drawRoundedRect(10, 4, 12, 18, 6, 6)
    p.drawLine(16, 22, 16, 27)
    p.drawLine(11, 27, 21, 27)
    if dot:
        p.setBrush(QColor(255, 50, 50))
        p.setPen(QColor(255, 255, 255))
        p.drawEllipse(20, 0, 12, 12)
    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# TrayController
# ---------------------------------------------------------------------------

_MENU_STYLE = """
QMenu {
    background-color: #2b2b2b;
    color: #f0f0f0;
    border: 1px solid #555555;
    padding: 4px 0px;
    font-size: 13px;
}
QMenu::item {
    padding: 7px 28px 7px 20px;
    border-radius: 3px;
    margin: 1px 4px;
}
QMenu::item:selected {
    background-color: #3d3d3d;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #888888;
}
QMenu::separator {
    height: 1px;
    background: #555555;
    margin: 3px 8px;
}
"""


class TrayController:
    def __init__(
        self,
        on_toggle_record: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_quit: Callable[[], None],
        on_open_data_folder: Callable[[], None],
        on_open_clipboard: Callable[[], None],
        on_check_update: Callable[[], None] | None = None,
    ) -> None:
        self._icon_idle      = _make_icon(QColor(120, 180, 255))
        self._icon_recording = _make_icon(QColor(255, 80, 80), dot=True)
        self._on_open_settings = on_open_settings
        self._on_toggle_record = on_toggle_record

        # Build QMenu — exec() is used (not popup/setContextMenu) because
        # exec() runs its own local event loop and is reliable on Windows 11.
        self._menu = QMenu()
        self._menu.setStyleSheet(_MENU_STYLE)
        self._menu.addAction("⚙  設定を開く",         on_open_settings)
        self._menu.addSeparator()
        self._menu.addAction("🎙  録音 開始/停止",     on_toggle_record)
        self._menu.addAction("📋  クリップボード履歴",  on_open_clipboard)
        self._menu.addSeparator()
        self._menu.addAction("📁  データフォルダを開く", on_open_data_folder)
        if on_check_update is not None:
            self._menu.addAction("🔄  更新を確認",        on_check_update)
        self._menu.addSeparator()
        self._menu.addAction("✕  終了",               on_quit)
        self._menu.addSeparator()
        _ver = self._menu.addAction(f"{__display_name__}  v{__version__}")
        _ver.setEnabled(False)  # non-clickable footer showing the version

        self.tray = QSystemTrayIcon(self._icon_idle)
        self.tray.setToolTip(f"{__display_name__}\n右クリック: メニュー\n左クリック: 録音")
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._on_toggle_record()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._on_open_settings()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            # exec() blocks (local event loop) until the user picks an item
            # or clicks outside — most reliable approach on Windows 11.
            self._menu.exec(QCursor.pos())

    def set_recording(self, recording: bool) -> None:
        self.tray.setIcon(self._icon_recording if recording else self._icon_idle)
        self.tray.setToolTip(
            f"{__display_name__} — 録音中\n左クリック: 停止"
            if recording else
            f"{__display_name__}\n右クリック: メニュー\n左クリック: 録音"
        )

    def notify(self, title: str, message: str) -> None:
        self.tray.showMessage(
            title, message, QSystemTrayIcon.MessageIcon.Information, 3000
        )

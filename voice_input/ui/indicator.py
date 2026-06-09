"""Recording indicator: a small always-on-top widget with a dancing polygon character.

The character is drawn programmatically (no external sprite needed). It bounces
and waves in sync with the live microphone level coming from the recorder.
"""
from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QMouseEvent, QPainter,
    QPainterPath, QPen, QPolygonF,
)
from PySide6.QtWidgets import QWidget


class DancingCharacter(QWidget):
    """A stylized polygon character that bounces/waves in response to audio level."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(110, 130)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._level = 0.0          # smoothed audio level (0..1)
        self._target_level = 0.0   # latest raw level
        self._phase = 0.0          # animation phase
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 fps

    def set_level(self, level: float) -> None:
        self._target_level = max(0.0, min(1.0, level))

    def _tick(self) -> None:
        # Exponential smoothing so it doesn't jitter.
        self._level += (self._target_level - self._level) * 0.4
        self._phase += 0.18
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx = w / 2

        # Bounce amplitude grows with audio level.
        bounce = math.sin(self._phase) * (4 + self._level * 18)
        sway = math.sin(self._phase * 0.7) * (2 + self._level * 8)

        base_y = h - 12
        body_top = base_y - 65 + bounce
        head_cy = body_top - 14

        # Shadow
        shadow_w = 42 - self._level * 6
        p.setBrush(QBrush(QColor(0, 0, 0, 70)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(int(cx), int(base_y + 4)), int(shadow_w / 2), 4)

        # Color shifts subtly with level for "energy"
        hue = 200 + self._level * 60  # blueish → purple
        body_color = QColor.fromHsvF((hue % 360) / 360.0, 0.65, 0.95)
        accent = QColor.fromHsvF(((hue + 30) % 360) / 360.0, 0.5, 1.0)

        # Body — diamond / polygon torso
        torso = QPolygonF([
            QPointF(cx + sway, body_top),                 # top
            QPointF(cx + 22 + sway * 0.7, body_top + 28), # right
            QPointF(cx + sway, body_top + 60),            # bottom
            QPointF(cx - 22 + sway * 0.7, body_top + 28), # left
        ])
        grad = QLinearGradient(QPointF(cx, body_top), QPointF(cx, body_top + 60))
        grad.setColorAt(0.0, accent)
        grad.setColorAt(1.0, body_color)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        p.drawPolygon(torso)

        # Head — hexagon
        head_r = 13
        head_poly = QPolygonF()
        for i in range(6):
            a = math.pi / 6 + i * math.pi / 3
            head_poly.append(QPointF(cx + sway + head_r * math.cos(a),
                                     head_cy + head_r * math.sin(a)))
        p.setBrush(QBrush(accent))
        p.drawPolygon(head_poly)

        # Eyes — two cyan dots, blink when level peaks
        eye_open = 0.0 if (self._level > 0.7 and math.sin(self._phase * 2) > 0.8) else 1.0
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(20, 30, 50)))
        eye_y = head_cy + 1
        if eye_open:
            p.drawEllipse(QPointF(cx + sway - 4, eye_y), 1.6, 2.0 * eye_open)
            p.drawEllipse(QPointF(cx + sway + 4, eye_y), 1.6, 2.0 * eye_open)
        else:
            p.setPen(QPen(QColor(20, 30, 50), 1.5))
            p.drawLine(QPointF(cx + sway - 5, eye_y), QPointF(cx + sway - 3, eye_y))
            p.drawLine(QPointF(cx + sway + 3, eye_y), QPointF(cx + sway + 5, eye_y))

        # Arms — waving lines, amplitude scales with level
        arm_phase = self._phase * 1.4
        arm_l_y = body_top + 18 + math.sin(arm_phase) * (3 + self._level * 14)
        arm_r_y = body_top + 18 + math.sin(arm_phase + math.pi) * (3 + self._level * 14)
        p.setPen(QPen(body_color, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - 22 + sway * 0.7, body_top + 28),
                   QPointF(cx - 38 + sway, arm_l_y))
        p.drawLine(QPointF(cx + 22 + sway * 0.7, body_top + 28),
                   QPointF(cx + 38 + sway, arm_r_y))

        # Legs — simple V
        p.setPen(QPen(body_color, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx + sway, body_top + 60),
                   QPointF(cx - 10 + sway * 0.5, base_y))
        p.drawLine(QPointF(cx + sway, body_top + 60),
                   QPointF(cx + 10 + sway * 0.5, base_y))


class IndicatorWindow(QWidget):
    """Floating frameless overlay: dancing character + REC text + audio bar + stop button."""

    stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(180, 200)

        self._character = DancingCharacter(self)
        self._character.move(35, 8)

        self._level = 0.0
        self._target_level = 0.0
        self._drag_offset: QPoint | None = None

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(33)

    def set_level(self, level: float) -> None:
        self._target_level = max(0.0, min(1.0, level))
        self._character.set_level(self._target_level)

    def _tick(self) -> None:
        self._level += (self._target_level - self._level) * 0.4
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # Backdrop card with rounded corners
        card_rect = QRect(4, 4, w - 8, h - 8)
        path = QPainterPath()
        path.addRoundedRect(card_rect, 16, 16)
        p.fillPath(path, QColor(15, 20, 35, 255))
        p.setPen(QPen(QColor(255, 80, 80, 200), 2))
        p.drawPath(path)

        # REC indicator dot + label
        dot_x, dot_y = 20, 150
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 60, 60)))
        p.drawEllipse(QPoint(dot_x, dot_y), 6, 6)
        p.setPen(QPen(QColor(255, 220, 220)))
        f = QFont()
        f.setBold(True)
        f.setPointSize(10)
        p.setFont(f)
        p.drawText(QRect(dot_x + 10, dot_y - 10, 100, 20), Qt.AlignVCenter, "REC")

        # Audio level meter (right of REC)
        bar_x = 70
        bar_y = dot_y - 6
        bar_w = 90
        bar_h = 12
        # Background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 30)))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 6, 6)
        # Foreground
        filled = max(2, int(bar_w * self._level))
        meter_color = QColor.fromHsv(int(120 - self._level * 120), 220, 240)
        p.setBrush(QBrush(meter_color))
        p.drawRoundedRect(bar_x, bar_y, filled, bar_h, 6, 6)

        # Stop button (bottom)
        btn_rect = QRect(36, 172, w - 72, 22)
        p.setBrush(QBrush(QColor(220, 50, 50, 220)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(btn_rect, 10, 10)
        p.setPen(QPen(Qt.white))
        f2 = QFont()
        f2.setPointSize(9)
        f2.setBold(True)
        p.setFont(f2)
        p.drawText(btn_rect, Qt.AlignCenter, "■ 停止 (Stop)")

        self._btn_rect = btn_rect

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            if hasattr(self, "_btn_rect") and self._btn_rect.contains(event.pos()):
                self.stop_requested.emit()
                return
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None

    def show_at(self, position: str, x: int = -1, y: int = -1) -> None:
        screen = self.screen() or self.windowHandle().screen() if self.windowHandle() else None
        if screen is None:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        margin = 24
        if position == "custom" and x >= 0 and y >= 0:
            self.move(x, y)
        elif position == "bottom-left":
            self.move(geo.left() + margin, geo.bottom() - self.height() - margin)
        elif position == "top-right":
            self.move(geo.right() - self.width() - margin, geo.top() + margin)
        elif position == "top-left":
            self.move(geo.left() + margin, geo.top() + margin)
        else:  # bottom-right (default)
            self.move(geo.right() - self.width() - margin, geo.bottom() - self.height() - margin)
        self.show()

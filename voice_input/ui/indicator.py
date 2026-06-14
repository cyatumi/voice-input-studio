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
        self._processing = False   # True while STT/refine runs ("翻訳中")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 fps

    def set_level(self, level: float) -> None:
        self._target_level = max(0.0, min(1.0, level))

    def set_processing(self, on: bool) -> None:
        self._processing = on

    def _tick(self) -> None:
        if self._processing:
            # Self-driven groove so the character keeps dancing while it
            # "thinks", even though no mic level arrives after recording stops.
            self._target_level = 0.45 + 0.22 * (math.sin(self._phase * 0.9) * 0.5 + 0.5)
        # Exponential smoothing so it doesn't jitter.
        self._level += (self._target_level - self._level) * 0.4
        self._phase += 0.18
        self.update()

    def _limb(self, p: QPainter, a: QPointF, b: QPointF, c: QPointF,
              color: QColor, width: float, joint_r: float = 2.4) -> None:
        """Draw a two-segment limb a→b→c with a rounded hand/foot dot at c."""
        p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([a, b, c]))
        if joint_r > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(c, joint_r, joint_r)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx = w / 2
        base_y = h - 10                      # feet line

        # Energy with a small noise gate: the character stays still during
        # silence and "wakes up" the moment you speak. The recorder's auto-gain
        # already suppresses silence to ~0, so only a light gate is needed here.
        # EVERY motion term below is scaled by `e`.
        GATE = 0.08
        e = max(0.0, (self._level - GATE) / (1.0 - GATE))

        t = self._phase
        beat = math.sin(t)

        # Cha-cha "dancing baby" groove — full body, every term scaled by e.
        sway = beat * e * 15                                # hips shift side to side
        bob  = (1.0 - math.cos(2 * t)) * 0.5 * e * 14       # body drops on each beat
        lean = beat * e * 0.22                              # torso leans into the sway

        hip_x = cx + sway
        hip_y = base_y - 42 + bob
        torso_len = 26
        sx = hip_x + math.sin(lean) * torso_len            # shoulder
        sy = hip_y - math.cos(lean) * torso_len
        neck = 14
        hx = sx + math.sin(lean) * neck                    # head centre
        hy = sy - math.cos(lean) * neck

        # Energy-driven colour (calm blue → vivid purple as it gets louder).
        hue = 200 + e * 90
        body_color = QColor.fromHsvF((hue % 360) / 360.0, 0.70, 0.97)
        accent     = QColor.fromHsvF(((hue + 35) % 360) / 360.0, 0.55, 1.0)

        # Shadow (squashes a touch as the body drops).
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 70)))
        p.drawEllipse(QPointF(cx + sway * 0.5, base_y + 5), 17 - bob * 0.15, 4)

        # --- Legs: alternating cha-cha steps; the off-weight foot lifts. ---
        lfoot = QPointF(cx - 11 + sway * 0.25, base_y - max(0.0,  beat) * e * 9)
        rfoot = QPointF(cx + 11 + sway * 0.25, base_y - max(0.0, -beat) * e * 9)
        lknee = QPointF((hip_x + lfoot.x()) / 2 - 4, (hip_y + lfoot.y()) / 2 + 5)
        rknee = QPointF((hip_x + rfoot.x()) / 2 + 4, (hip_y + rfoot.y()) / 2 + 5)
        self._limb(p, QPointF(hip_x, hip_y), lknee, lfoot, body_color, 4.0)
        self._limb(p, QPointF(hip_x, hip_y), rknee, rfoot, body_color, 4.0)

        # --- Torso: tapered body from hips to shoulders, leaning with the beat.
        perp_x, perp_y = math.cos(lean), math.sin(lean)
        hipw, shw = 11.0, 9.0
        torso = QPolygonF([
            QPointF(hip_x - perp_x * hipw, hip_y - perp_y * hipw),
            QPointF(sx - perp_x * shw,     sy - perp_y * shw),
            QPointF(sx + perp_x * shw,     sy + perp_y * shw),
            QPointF(hip_x + perp_x * hipw, hip_y + perp_y * hipw),
        ])
        grad = QLinearGradient(QPointF(hip_x, hip_y), QPointF(sx, sy))
        grad.setColorAt(0.0, body_color)
        grad.setColorAt(1.0, accent)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 190), 1.5))
        p.drawPolygon(torso)

        # --- Arms: bent-elbow pump, swinging in opposition. ---
        swing = math.sin(t + math.pi / 3)
        lhand = QPointF(sx - 15 - e * 3, sy - 4 - swing * e * 18)
        rhand = QPointF(sx + 15 + e * 3, sy - 4 + swing * e * 18)
        lelbow = QPointF((sx + lhand.x()) / 2 - 5, (sy + lhand.y()) / 2 + 4)
        relbow = QPointF((sx + rhand.x()) / 2 + 5, (sy + rhand.y()) / 2 + 4)
        self._limb(p, QPointF(sx, sy), lelbow, lhand, accent, 3.5)
        self._limb(p, QPointF(sx, sy), relbow, rhand, accent, 3.5)

        # --- Head: round (baby-like), with a soft outline. ---
        head_r = 11
        p.setPen(QPen(QColor(255, 255, 255, 150), 1.2))
        p.setBrush(QBrush(accent))
        p.drawEllipse(QPointF(hx, hy), head_r, head_r)

        # Eyes — blink at energetic peaks.
        blink = (e > 0.6 and math.sin(self._phase * 2) > 0.85)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(20, 30, 50)))
        ey = hy - 1
        if not blink:
            p.drawEllipse(QPointF(hx - 4, ey), 1.7, 2.2)
            p.drawEllipse(QPointF(hx + 4, ey), 1.7, 2.2)
        else:
            p.setPen(QPen(QColor(20, 30, 50), 1.5))
            p.drawLine(QPointF(hx - 5.5, ey), QPointF(hx - 2.5, ey))
            p.drawLine(QPointF(hx + 2.5, ey), QPointF(hx + 5.5, ey))

        # Mouth — opens up ("singing!") as the energy rises.
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(20, 30, 50)))
        p.drawEllipse(QPointF(hx, hy + 5), 2.2, 1.0 + e * 3.0)

        # "Thinking" dots above the head while a translation is in progress.
        if self._processing:
            p.setPen(Qt.NoPen)
            for i in range(3):
                pulse = max(0.0, math.sin(self._phase * 2.0 - i * 0.7))
                r = 1.5 + 2.0 * pulse
                p.setBrush(QBrush(QColor(120, 200, 255, int(120 + 135 * pulse))))
                p.drawEllipse(QPointF(hx - 8 + i * 8, hy - head_r - 9), r, r)


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
        self._phase = 0.0
        self._processing = False
        self._drag_offset: QPoint | None = None

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(33)

    def set_level(self, level: float) -> None:
        self._target_level = max(0.0, min(1.0, level))
        self._character.set_level(self._target_level)

    def set_processing(self, on: bool) -> None:
        """Switch between REC (recording) and 翻訳中 (transcribing) display."""
        self._processing = on
        self._character.set_processing(on)
        if on:
            self._target_level = 0.0
        self.update()

    def _tick(self) -> None:
        self._level += (self._target_level - self._level) * 0.4
        self._phase += 0.12
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

        if self._processing:
            # --- 翻訳中 (transcribing) state: calm border + indeterminate bar ---
            p.setPen(QPen(QColor(90, 180, 255, 220), 2))
            p.drawPath(path)

            ndots = int(self._phase * 3) % 4
            p.setPen(QPen(QColor(190, 225, 255)))
            f = QFont()
            f.setBold(True)
            f.setPointSize(11)
            p.setFont(f)
            p.drawText(QRect(16, 140, w - 32, 22),
                       Qt.AlignVCenter | Qt.AlignHCenter,
                       "翻訳中" + "." * ndots)

            # Indeterminate bar that sweeps left↔right.
            bar_x, bar_y, bar_w, bar_h = 20, 174, w - 40, 10
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, 30)))
            p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 5, 5)
            seg = 46
            pos = int((math.sin(self._phase) * 0.5 + 0.5) * (bar_w - seg))
            p.setBrush(QBrush(QColor(90, 180, 255)))
            p.drawRoundedRect(bar_x + pos, bar_y, seg, bar_h, 5, 5)

            self._btn_rect = QRect()   # no stop button while translating
            return

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

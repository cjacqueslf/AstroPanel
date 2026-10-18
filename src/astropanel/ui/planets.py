from datetime import timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget, QToolTip

from astropanel.ui.widgets import Card


class PlanetTimeline(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(280, 410)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.night = None
        self.now = None
        self.red_mode = False

    def paintEvent(self, event):
        if self.night is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(1, min(1, self.height() / 410))
        fg = QColor("#ff8b8b" if self.red_mode else "#e5f2f7")
        muted = QColor("#be7373" if self.red_mode else "#aac1d2")
        left, right = 80, self.width() - 43
        start, end = self.night.moments[0], self.night.moments[-1]
        total = (end - start).total_seconds()

        def x(moment):
            return left + (moment - start).total_seconds() / total * (right - left)

        p.setPen(muted)
        ticks = 5 if self.width() >= 420 else 3
        for i in range(ticks):
            moment = start + (end - start) * i / (ticks - 1)
            rect = QRectF(x(moment) - 17, 0, 34, 20)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, moment.astimezone(self.tz).strftime("%Hh"))
        for row, track in enumerate(self.night.tracks):
            y = 28 + row * 40
            p.setPen(fg)
            p.drawText(QRectF(0, y, 77, 25), Qt.AlignmentFlag.AlignVCenter, track.name)
            p.fillRect(QRectF(left, y + 4, right - left, 18), QColor("#291c1c" if self.red_mode else "#1c2e40"))
            for windows, color in ((track.above_horizon, "#795454" if self.red_mode else "#6a829b"),
                                   (track.favorable, "#e35050" if self.red_mode else "#46b7a0")):
                for window in windows:
                    p.fillRect(QRectF(x(window.start), y + 4, x(window.end) - x(window.start), 18), QColor(color))
            if self.now:
                position = max(0, min(144, (self.now - start).total_seconds() / total * 144))
                index = min(143, int(position))
                height = track.altitudes[index] + (track.altitudes[index + 1] - track.altitudes[index]) * (position - index)
                p.setPen(fg)
                p.drawText(QRectF(right + 4, y, 39, 25), Qt.AlignmentFlag.AlignVCenter, f"{height:.0f}°")
        footer_y = 28 + len(self.night.tracks) * 40
        if self.now:
            current_x = max(left, min(right, x(self.now)))
            p.setPen(QPen(fg, 1.5))
            p.drawLine(int(current_x), 24, int(current_x), footer_y - 1)
            p.drawText(QRectF(0, footer_y, self.width(), 20), Qt.AlignmentFlag.AlignCenter,
                       f"Agora · {self.now.astimezone(self.tz):%H:%M:%S}")

    def mouseMoveEvent(self, event):
        if self.night is None:
            return
        scale = min(1, self.height() / 410)
        row = int((event.position().y() / scale - 28) // 40)
        if 0 <= row < len(self.night.tracks):
            track = self.night.tracks[row]
            windows = track.above_horizon if track.name == "Sol" else track.favorable
            criterion = "acima do horizonte" if track.name == "Sol" else "acima de 20° e Sol abaixo de −6°"
            periods = "\n".join(f"{w.start.astimezone(self.tz):%d/%m %H:%M} → {w.end.astimezone(self.tz):%d/%m %H:%M}" for w in windows)
            QToolTip.showText(event.globalPosition().toPoint(), f"{track.name} · {criterion}\n{periods or 'Sem intervalo favorável nesta noite.'}", self)
        else:
            QToolTip.hideText()


class PlanetVisibilityPanel(Card):
    def __init__(self):
        super().__init__("Visibilidade de Planetas")
        self.caption = QLabel()
        self.caption.setObjectName("locationName")
        self.caption.setWordWrap(True)
        self.body.addWidget(self.caption)
        self.chart = PlanetTimeline()
        self.body.addWidget(self.chart, 1)
        legend = QLabel("Azul claro: acima do horizonte · Destaque: altitude >20° e Sol <−6°\nÀ direita: altitude atual. Horários no fuso do observatório.")
        legend.setObjectName("locationName")
        legend.setWordWrap(True)
        self.body.addWidget(legend)
        self.setToolTip("Visibilidade geométrica aproximada. Não considera nuvens, obstáculos, brilho do céu ou equipamento. Passe sobre um planeta para ver seus intervalos favoráveis.")

    def set_night(self, night, location, day):
        self.chart.night = night
        self.chart.tz = ZoneInfo(location.timezone)
        self.caption.setText(f"Noite de {day:%d/%m/%Y} · {location.name}")
        self.chart.update()

    def set_now(self, moment, red_mode=False):
        self.chart.now = moment.astimezone(timezone.utc)
        self.chart.red_mode = red_mode
        self.chart.update()

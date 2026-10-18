from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import elevation
from astral.moon import elevation as lunar_elevation
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from astropanel.services.astronomy import calculate_sun_moon, moonless_status
from astropanel.ui.widgets import Card


class NightTimelineChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(250, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.start = self.end = self.now = None
        self.solar = ()
        self.lunar = ()
        self.windows = ()
        self.red_mode = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(1, min(1, self.height() / 190))
        if self.start is None:
            return
        foreground = QColor("#ff8b8b" if self.red_mode else "#e5f2f7")
        muted = QColor("#c87979" if self.red_mode else "#aac1d2")
        left, width = 8, self.width() - 16
        span = (self.end - self.start).total_seconds()

        def x(moment):
            return left + (moment.astimezone(timezone.utc) - self.start).total_seconds() / span * width

        painter.setPen(muted)
        for i in range(5):
            moment = self.start + (self.end - self.start) * i / 4
            label = moment.astimezone(self.tz).strftime("%Hh")
            rect = QRectF(left + i * width / 4 - 20, 0, 40, 20)
            if i == 0:
                rect.moveLeft(left)
            elif i == 4:
                rect.moveRight(left + width)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        lanes = (("Sol · dia / crepúsculos / noite", self.solar),
                 ("Lua · acima do horizonte", self.lunar),
                 ("Observação sem Lua", None))
        colors = ("#c79959", "#926442", "#57758a", "#324568", "#16253e")
        if self.red_mode:
            colors = ("#a65151", "#874242", "#693434", "#4d2929", "#301c1c")
        for row, (label, samples) in enumerate(lanes):
            y = 27 + row * 49
            painter.setPen(foreground)
            painter.drawText(QRectF(left, y, width, 20), Qt.AlignmentFlag.AlignLeft, label)
            track = QRectF(left, y + 22, width, 18)
            painter.fillRect(track, QColor("#251717" if self.red_mode else "#1c2e40"))
            if row == 0:
                for i, value in enumerate(samples):
                    category = 0 if value >= 0 else 1 if value >= -6 else 2 if value >= -12 else 3 if value >= -18 else 4
                    painter.fillRect(QRectF(left + i / len(samples) * width, track.top(), width / len(samples) + .5, 18), QColor(colors[category]))
            elif row == 1:
                # Interpolate the 15-minute lunar samples to locate horizon crossings.
                for i, (a, b) in enumerate(zip(samples, samples[1:])):
                    begin, finish = i / (len(samples) - 1), (i + 1) / (len(samples) - 1)
                    if a < 0 and b < 0:
                        continue
                    if (a < 0) != (b < 0):
                        crossing = begin + (-a / (b - a)) * (finish - begin)
                        if a < 0:
                            begin = crossing
                        else:
                            finish = crossing
                    painter.fillRect(QRectF(left + begin * width, track.top(), (finish - begin) * width, 18), QColor("#bb6666" if self.red_mode else "#829eb8"))
            else:
                for window in self.windows:
                    painter.fillRect(QRectF(x(window.start), track.top(), x(window.end) - x(window.start), 18), QColor("#e35050" if self.red_mode else "#46b7a0"))
        if self.now:
            current_x = max(left, min(left + width, x(self.now)))
            painter.setPen(QPen(foreground, 1.5))
            painter.drawLine(int(current_x), 23, int(current_x), 165)
            painter.drawText(QRectF(left, 168, width, 20), Qt.AlignmentFlag.AlignCenter,
                             f"Agora · {self.now.astimezone(self.tz):%H:%M:%S}")


class NightTimelinePanel(Card):
    def __init__(self, parent=None):
        super().__init__("Linha do Tempo", parent)
        self.summary = QLabel()
        self.summary.setObjectName("locationName")
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)
        self.chart = NightTimelineChart()
        self.body.addWidget(self.chart, 1)
        self.events = QLabel()
        self.events.setObjectName("locationName")
        self.events.setWordWrap(True)
        self.body.addWidget(self.events)
        self.status = QLabel()
        self.status.setObjectName("locationName")
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)
        self.setToolTip("Horários no fuso do observatório. Faixas solares e lunares aproximadas; janelas sem Lua calculadas pelos cruzamentos do horizonte.")

    def set_night(self, location, day, lunar, windows):
        tz = ZoneInfo(location.timezone)
        local_start = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=12)
        local_end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=tz) + timedelta(hours=12)
        chart = self.chart
        chart.tz = tz
        chart.start, chart.end = local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)
        observer = Observer(location.latitude, location.longitude, location.altitude_m)
        chart.solar = tuple(elevation(observer, chart.start + (chart.end - chart.start) * (i + .5) / 288,
                                      with_refraction=False) for i in range(288))
        # On DST transitions, evenly space samples in UTC along the actual span.
        if (chart.end - chart.start).total_seconds() != 86400:
            lunar = tuple(lunar_elevation(observer, chart.start + (chart.end - chart.start) * i / 96) for i in range(97))
        chart.lunar, chart.windows = lunar, windows
        today, tomorrow = calculate_sun_moon(location, day), calculate_sun_moon(location, day + timedelta(days=1))
        total = round(sum(w.duration.total_seconds() for w in windows) / 60)
        self.summary.setText(f"Noite de {day:%d/%m/%Y} · Sem Lua: {total // 60}h {total % 60:02}min")
        named_events = []
        for info in (today, tomorrow):
            for name, moment in (("Pôr do Sol", info.sunset), ("Noite começa", info.astro_dusk),
                                 ("Lua nasce", info.moonrise), ("Lua se põe", info.moonset),
                                 ("Noite termina", info.astro_dawn), ("Sol nasce", info.sunrise)):
                if moment and chart.start <= moment.astimezone(timezone.utc) < chart.end:
                    named_events.append((moment, name))
        self.events.setText(" · ".join(f"{name} {moment:%d/%m %H:%M}" for moment, name in sorted(named_events))
                            or "Sem eventos de horizonte neste período.")

    def set_now(self, moment, red_mode=False):
        self.chart.now = moment
        self.chart.red_mode = red_mode
        self.chart.update()
        self.status.setText(moonless_status(self.chart.windows, moment))

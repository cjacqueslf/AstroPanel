"""Asynchronous seeing monitor for the configured observing site."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import Qt, QTimer, QUrl, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QHeaderView

from astropanel.services.seeing import forecast_url, parse_forecast, TRANSPARENCY_BANDS
from astropanel.ui.widgets import Card

COLOURS = ('#50d7ba', '#50d7ba', '#78bfef', '#78bfef', '#f3c56c', '#f3c56c', '#ed8585', '#ed8585')

class SeeingChart(QWidget):
    def __init__(self):
        super().__init__()
        self.samples = []
        self.zone = ZoneInfo('UTC')
        self.setMinimumSize(300, 100)
        self.setToolTip('Evolução do seeing previsto. Barras menores indicam menor turbulência. Escala de categorias 1–8.')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#071019'))
        painter.setPen(QColor('#c5d5e0'))
        painter.drawText(8, 17, 'SEEING · menor é melhor')
        if not self.samples:
            painter.drawText(8, 50, 'Aguardando previsão…')
            return
        top, bottom = 24, self.height() - 24
        step = (self.width() - 16) / len(self.samples)
        for i, sample in enumerate(self.samples):
            height = (bottom - top) * sample.seeing / 8
            painter.fillRect(QRectF(8 + i * step, bottom - height, max(1, step - 3), height), QColor(COLOURS[sample.seeing - 1]))
            if i % max(1, len(self.samples) // 4) == 0:
                painter.setPen(QColor('#c5d5e0'))
                painter.drawText(int(8 + i * step), self.height() - 7, sample.time.astimezone(self.zone).strftime('%d/%m %Hh'))

class SeeingPanel(Card):
    def __init__(self):
        super().__init__('Seeing · estabilidade atmosférica')
        self.location = None
        self.samples = []
        self.issued = None
        self.received = None
        self.reply = None
        self.manager = QNetworkAccessManager(self)
        self.zone = ZoneInfo('UTC')
        self.site = QLabel(); self.site.setWordWrap(True)
        self.summary = QLabel('Selecione este painel para consultar a previsão.')
        self.summary.setWordWrap(True)
        self.summary.setObjectName('seeingSummary')
        self.chart = SeeingChart()
        self.table = QTableWidget(0, 4)
        self.table.setObjectName('seeingForecast')
        self.table.setHorizontalHeaderLabels(['Horário local', 'Seeing', 'Nuvens', 'Transparência'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumSize(350, 120)
        self.status = QLabel(); self.status.setWordWrap(True)
        self.note = QLabel('Previsão 7Timer! / GFS · seeing em segundos de arco (″).\nTransparência em mag/massa de ar; menor é melhor. Não é medição local.')
        self.note.setWordWrap(True)
        for label in (self.site, self.status, self.note):
            label.setObjectName('locationName')
        self.update_button = QPushButton('Atualizar seeing')
        self.update_button.setObjectName('settingsButton')
        self.update_button.clicked.connect(self.refresh_forecast)
        row = QHBoxLayout(); row.addWidget(self.site, 1); row.addWidget(self.update_button)
        self.body.addLayout(row)
        for widget in (self.summary, self.chart, self.table, self.status, self.note):
            self.body.addWidget(widget)
        self.body.setStretchFactor(self.chart, 1)
        self.body.setStretchFactor(self.table, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(30 * 60 * 1000)
        self.timer.timeout.connect(self.refresh_forecast)
        self.clock = QTimer(self)
        self.clock.setInterval(60000)
        self.clock.timeout.connect(self.render_forecast)

    def set_location(self, location, enabled=True):
        changed = self.location != location
        self.location = location
        try:
            self.zone = ZoneInfo(location.timezone)
        except (ValueError, ZoneInfoNotFoundError):
            self.zone = ZoneInfo('UTC')
        self.site.setText(f'{location.name} · {location.latitude:.3f}, {location.longitude:.3f}')
        if changed:
            if self.reply:
                old, self.reply = self.reply, None
                old.abort()
            self.samples = []; self.issued = self.received = None
            self.render_forecast()
        if enabled:
            self.timer.start(); self.clock.start()
            if changed or not self.samples:
                self.refresh_forecast()
        else:
            self.timer.stop(); self.clock.stop()
            if self.reply:
                old, self.reply = self.reply, None
                old.abort()

    def refresh_forecast(self):
        if self.location is None or self.reply is not None:
            return
        request = QNetworkRequest(QUrl(forecast_url(self.location)))
        request.setTransferTimeout(20000)
        reply = self.manager.get(request)
        self.reply = reply
        self.status.setText('Consultando previsão de seeing…')
        self.update_button.setEnabled(False)
        reply.finished.connect(lambda: self._finished(reply))

    def _finished(self, reply):
        if reply is not self.reply:
            reply.deleteLater()
            self.update_button.setEnabled(self.reply is None)
            return
        self.reply = None
        self.update_button.setEnabled(True)
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(reply.errorString())
            self.issued, samples = parse_forecast(json.loads(bytes(reply.readAll())))
            self.samples = samples
            self.received = datetime.now(timezone.utc)
            self.render_forecast()
        except (ValueError, TypeError, KeyError, OverflowError):
            self.render_forecast()
            self.status.setText('Falha na atualização. ' + ('Exibindo previsão anterior; confira sua idade.' if self.samples else 'Previsão indisponível.') + ' Tente novamente.')
        finally:
            reply.deleteLater()

    def render_forecast(self):
        now = datetime.now(timezone.utc)
        future = [s for s in self.samples if s.time + timedelta(hours=3) > now]
        self.chart.samples = future; self.chart.zone = self.zone; self.chart.update()
        self.table.setRowCount(len(future))
        for index, sample in enumerate(future):
            values = (sample.time.astimezone(self.zone).strftime('%d/%m %H:%M'), sample.seeing_text,
                      sample.cloud_text + (' · precip.' if sample.rain else ''),
                      TRANSPARENCY_BANDS[sample.transparency - 1])
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setForeground(QColor(COLOURS[sample.seeing - 1]))
                self.table.setItem(index, column, item)
        if not future:
            self.summary.setText('Sem previsão válida para este horário')
        else:
            sample = future[0]
            self.summary.setText(f'{sample.quality} · {sample.seeing_text} · {sample.time.astimezone(self.zone):%d/%m %H:%M}')
            best = min(future[:8], key=lambda s: (s.seeing, s.clouds, s.transparency))
            self.summary.setToolTip(f'Menor seeing nos próximos horários: {best.time.astimezone(self.zone):%d/%m %H:%M} · {best.seeing_text}. Confira nuvens e precipitação.')
        if self.issued:
            age = max(0, int((now - self.issued).total_seconds() / 3600))
            warning = ' · PREVISÃO ANTIGA' if age > 12 else ''
            self.status.setText(f'Modelo: {self.issued.astimezone(self.zone):%d/%m %H:%M} · idade {age} h{warning} · consulta {self.received.astimezone(self.zone):%H:%M}')
        else:
            self.status.setText('Previsão indisponível. Use Atualizar seeing.')

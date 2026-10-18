"""Solar images and activity, fetched independently without blocking the UI."""
import json
import re
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from astral import Observer
from astral.sun import elevation
from PySide6.QtCore import Qt, QTimer, QUrl, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (QWidget, QLabel, QHBoxLayout, QPushButton, QVBoxLayout,
    QDialog, QGraphicsView, QGraphicsScene)
from astropanel.services.solar import (SDO_IMAGE, SDO_TIME, NOAA_ROOT,
    gong_time, latest_record, region_summary, observation_stamp, gong_metadata_path)
from astropanel.ui.widgets import Card

class SolarImageViewer(QDialog):
    def __init__(self, source):
        # Use the real application window as owner, not the embedded panel.
        owner = source.window()
        proxy = owner.graphicsProxyWidget()
        if proxy is not None and proxy.scene() is not None:
            views = proxy.scene().views()
            if views:
                owner = views[0].window()
        flags = Qt.WindowType.Dialog | Qt.WindowType.BypassGraphicsProxyWidget
        if owner.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(owner, flags)
        self.setWindowTitle(source.title + ' · imagem ampliada')
        self.resize(950, 900)
        layout = QVBoxLayout(self)
        self.info = QLabel(source.description + '\n' + source.message)
        layout.addWidget(self.info)
        self.scene = QGraphicsScene(self)
        self.scene.addPixmap(QPixmap.fromImage(source.viewer_image()))
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(QColor('#071019'))
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        layout.addWidget(self.view, 1)
        controls = QHBoxLayout()
        for text, callback in (
            ('−', lambda: self.view.scale(0.8, 0.8)),
            ('+', lambda: self.view.scale(1.25, 1.25)),
            ('Ajustar à janela', self.fit_image),
            ('100%', self.view.resetTransform),
            ('Fechar', self.close)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        layout.addWidget(QLabel('Use + / − para ampliar e arraste a imagem para examinar os detalhes.'))

    def fit_image(self):
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_image()


class SolarImage(QWidget):
    def __init__(self, title, description):
        super().__init__()
        self.title = title
        self.description = description
        self.image = QImage()
        self.message = 'Aguardando imagem…'
        self.url = ''
        self.stamp = ''
        self.viewer = None
        self.setMinimumSize(190, 210)
        self.setToolTip(description + ' · Clique para ampliar e usar o zoom.')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor('#071019'))
        if not self.image.isNull():
            area = self.rect().adjusted(0, 22, 0, -35)
            size = self.image.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF(area.center().x() - size.width()/2, area.center().y() - size.height()/2,
                            size.width(), size.height())
            painter.drawImage(target, self.image)
        painter.setPen(QColor('#e5f2f7'))
        painter.drawText(self.rect().adjusted(7, 3, -7, -3), Qt.AlignmentFlag.AlignTop, self.title)
        painter.drawText(self.rect().adjusted(7, 25, -7, -4),
                         Qt.AlignmentFlag.AlignBottom | Qt.TextFlag.TextWordWrap, self.message)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.image.isNull():
            self.open_viewer()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def viewer_image(self):
        return self.image

    def open_viewer(self):
        if self.viewer is not None:
            self.viewer.close()
            self.viewer.deleteLater()
        self.viewer = SolarImageViewer(self)
        self.viewer.show()
        self.viewer.raise_()
        self.viewer.activateWindow()

class SolarObservingPanel(Card):
    def __init__(self):
        super().__init__('Observação solar')
        self.location = None
        self.enabled = False
        self.started = False
        self.generation = 0
        self.pending = {}
        self.manager = QNetworkAccessManager(self)
        self.local_info = QLabel(); self.local_info.setWordWrap(True)
        self.update_button = QPushButton('Atualizar Sol'); self.update_button.setObjectName('settingsButton')
        self.update_button.clicked.connect(self.refresh_data)
        header = QHBoxLayout(); header.addWidget(self.local_info, 1); header.addWidget(self.update_button)
        self.body.addLayout(header)
        self.visible = SolarImage('Visível · SDO/HMI', 'Contínuo visível: fotosfera e manchas solares')
        self.halpha = SolarImage('H-alfa · GONG / NSO', 'H-alfa 656,28 nm: cromosfera, filamentos e proeminências')
        images = QHBoxLayout(); images.addWidget(self.visible, 1); images.addWidget(self.halpha, 1)
        self.body.addLayout(images, 1)
        self.regions = QLabel('Regiões ativas / manchas: aguardando NOAA…')
        self.flux = QLabel('Fluxo F10.7: aguardando NOAA…')
        self.flares = QLabel('Raios X / erupções: aguardando GOES…')
        self.status = QLabel('Fontes: NASA/SDO · NSO/GONG · NOAA/SWPC')
        for label in (self.local_info, self.regions, self.flux, self.flares, self.status):
            label.setObjectName('locationName'); label.setWordWrap(True)
        for label in (self.regions, self.flux, self.flares, self.status):
            self.body.addWidget(label)
        self.timer = QTimer(self); self.timer.setInterval(10 * 60 * 1000)
        self.timer.timeout.connect(self.refresh_data)
        self.local_timer = QTimer(self); self.local_timer.setInterval(60000)
        self.local_timer.timeout.connect(self.update_local)

    def set_location(self, location, enabled=True):
        self.location = location
        self.enabled = enabled
        self.update_local()
        if enabled:
            self.timer.start(); self.local_timer.start()
            if not self.started:
                self.refresh_data()
        else:
            self.timer.stop(); self.local_timer.stop()
            self.generation += 1
            replies = list(self.pending.values()); self.pending.clear()
            for reply in replies:
                reply.abort()
            self.update_button.setEnabled(True)

    def update_local(self):
        if self.location:
            loc = self.location
            altitude = elevation(Observer(loc.latitude, loc.longitude, loc.altitude_m), datetime.now(timezone.utc))
            self.local_info.setText(f'{loc.name} · Sol a {altitude:.1f}° · ' +
                                    ('acima do horizonte' if altitude > 0 else 'abaixo do horizonte'))

    def _get(self, key, url, handler, failed=None):
        if key in self.pending:
            return
        request = QNetworkRequest(QUrl(url)); request.setTransferTimeout(20000)
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute, QNetworkRequest.CacheLoadControl.AlwaysNetwork)
        reply = self.manager.get(request); self.pending[key] = reply
        generation = self.generation
        self.update_button.setEnabled(False)
        def finished():
            if generation != self.generation:
                reply.deleteLater(); return
            self.pending.pop(key, None)
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise ValueError(reply.errorString())
                handler(bytes(reply.readAll()))
            except (ValueError, KeyError, TypeError, OverflowError):
                if failed:
                    failed()
            finally:
                reply.deleteLater()
                self.update_button.setEnabled(not self.pending)
                if not self.pending:
                    self.status.setText('Consulta: ' + datetime.now(timezone.utc).strftime('%d/%m %H:%M UTC') + ' · NASA / NSO / NOAA')
        deadline = QTimer(reply)
        deadline.setSingleShot(True)
        deadline.timeout.connect(reply.abort)
        reply.finished.connect(deadline.stop)
        deadline.start(30000)
        reply.finished.connect(finished)

    def refresh_data(self):
        if self.pending:
            return
        self.started = True
        self.update_local()
        self.status.setText('Atualizando imagens e atividade solar…')
        self._get('visible', SDO_IMAGE, lambda data: self._image(self.visible, data, SDO_IMAGE),
                  lambda: self._image_failed(self.visible))
        self._get('visible_time', SDO_TIME, self._sdo_time)
        self._gong_today()
        for key, endpoint, handler, label in (
            ('regions', 'solar_regions.json', self._regions, self.regions),
            ('flux', 'f107_cm_flux.json', self._flux, self.flux),
            ('flares', 'goes/primary/xray-flares-latest.json', self._flares, self.flares)):
            self._get(key, NOAA_ROOT + endpoint, lambda data, callback=handler: callback(json.loads(data)),
                      lambda target=label: self._data_failed(target))

    def _gong_today(self):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        results = []
        remaining = [5]
        def received(data=None):
            if data is not None:
                try:
                    results.append(gong_metadata_path(data))
                except ValueError:
                    pass
            remaining[0] -= 1
            if remaining[0]:
                return
            if not results:
                self._image_failed(self.halpha)
                return
            path = max(results, key=lambda p: p.rsplit('/', 1)[-1])
            url = 'https://gong2.nso.edu' + path
            stamp = gong_time(path.rsplit('/', 1)[-1])
            self.halpha.message = 'Carregando H-alfa…'; self.halpha.update()
            def loaded(content):
                self._image(self.halpha, content, url)
                self.halpha.message = observation_stamp(stamp.isoformat()); self.halpha.update()
            self._get('gong_image', url, loaded, lambda: self._image_failed(self.halpha))
        for site in 'CTLBU':
            query = urlencode(dict(dir='/HA/hav', num=1, fileStr=site + 'h.jpg', skip=1,
                syr=start.year, smn=start.month, sdy=start.day,
                eyr=now.year, emn=now.month, edy=now.day))
            url = 'https://gong2.nso.edu/products/scaleView/getMostRecentN.php?' + query
            self._get('gong_meta_' + site, url, received, received)

    def _image(self, target, data, url):
        image = QImage.fromData(data)
        if image.isNull():
            raise ValueError('Imagem inválida')
        target.image = image; target.url = url
        if target is self.visible:
            target.message = target.stamp or 'Imagem recebida · horário na imagem'
        target.update()

    def _image_failed(self, target):
        target.message = 'Falha na atualização' + (' · imagem anterior' if not target.image.isNull() else ' · indisponível')
        target.update()

    def _data_failed(self, target):
        text = target.text().split(' · falha na atualização')[0]
        target.setText(text + ' · falha na atualização')

    def _sdo_time(self, data):
        text = data.decode('utf-8', errors='replace')
        match = re.search(r'(?:continuum|HMIIC):\s*(\d{8})_(\d{6})', text)
        if not match:
            raise ValueError('Horário SDO ausente')
        stamp = datetime.strptime(''.join(match.groups()), '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        self.visible.stamp = observation_stamp(stamp.isoformat())
        self.visible.message = self.visible.stamp
        self.visible.update()
        self.visible.setToolTip(self.visible.description + '\nSDO/HMI: ' + self.visible.stamp + '\nClique para ampliar e usar o zoom.')

    def _regions(self, rows):
        date, spots, regions = region_summary(rows)
        stamp = observation_stamp(date)
        details = ' · '.join(f"AR {r['region']}: {r.get('number_spots') if r.get('number_spots') is not None else '—'} manchas / {r.get('mag_class') or '—'}" for r in regions[:3])
        incomplete = ' · contagem parcial' if any(r.get('number_spots') is None for r in regions) else ''
        self.regions.setText(f'{len(regions)} regiões ativas · {spots} manchas reportadas{incomplete} (não é índice de Wolf)\n{details}\nNOAA: {stamp}')

    def _flux(self, rows):
        row = latest_record(rows)
        value = row.get('flux')
        if value is None:
            raise ValueError('Fluxo ausente')
        self.flux.setText(f"F10.7: {value:g} sfu · NOAA: {observation_stamp(row['time_tag'])}")

    def _flares(self, rows):
        row = latest_record(rows)
        self.flares.setText(f"Raios X GOES: {row.get('current_class') or '—'} · {observation_stamp(row['time_tag'])}\n"
                            f"Último pico informado: {row.get('max_class') or '—'} · {observation_stamp(row['max_time']) if row.get('max_time') else 'sem horário'}")

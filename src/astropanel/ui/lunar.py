"""Lunar observing card with an hourly, phase-matched NASA atlas."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from astral import Observer
from astral.moon import elevation
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QImage, QPixmap, QColor, QPainter
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout
from astropanel.services.lunar import LUNAR_API, lunar_hour, lunar_sources, lunar_phase_name
from astropanel.ui.solar import SolarImage
from astropanel.ui.widgets import Card


class LunarImage(SolarImage):
    def __init__(self):
        super().__init__('Lua · NASA / LRO', 'Mapa lunar com mares e crateras · norte para cima')
        self.atlas = QImage()
        self.atlas_status = 'Carregando mapa com nomes…'

    def viewer_image(self):
        return self.atlas

    def open_viewer(self):
        super().open_viewer()
        self.update_viewer()

    def update_viewer(self):
        if self.viewer is None:
            return
        self.viewer.info.setText(self.description + '\n' + self.message)
        self.viewer.scene.clear()
        if self.atlas.isNull():
            item = self.viewer.scene.addText(self.atlas_status)
            item.setDefaultTextColor(QColor('#e5f2f7'))
        else:
            self.viewer.scene.addPixmap(QPixmap.fromImage(self.atlas))
        self.viewer.fit_image()


class LunarObservingPanel(Card):
    def __init__(self):
        super().__init__('Observação lunar')
        self.location = None
        self.enabled = False
        self.generation = 0
        self.pending = {}
        self.last_hour = None
        self.manager = QNetworkAccessManager(self)
        self.local_info = QLabel()
        self.update_button = QPushButton('Atualizar Lua')
        self.update_button.setObjectName('settingsButton')
        self.update_button.clicked.connect(self.refresh_data)
        header = QHBoxLayout()
        header.addWidget(self.local_info, 1)
        header.addWidget(self.update_button)
        self.body.addLayout(header)
        self.moon = LunarImage()
        self.body.addWidget(self.moon, 1)
        self.phase = QLabel('Fase e iluminação: aguardando NASA…')
        self.details = QLabel('Clique na Lua para ver os nomes dos mares e crateras com zoom.')
        self.status = QLabel('Fonte: NASA SVS / LRO · simulação da fase e libração · atualização horária')
        for label in (self.local_info, self.phase, self.details, self.status):
            label.setObjectName('locationName')
            label.setWordWrap(True)
        for label in (self.phase, self.details, self.status):
            self.body.addWidget(label)
        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(self.tick)

    def set_location(self, location, enabled=True):
        self.location = location
        self.enabled = enabled
        self.update_local()
        if enabled:
            self.timer.start()
            self.tick()
        else:
            self.timer.stop()
            self.generation += 1
            replies = list(self.pending.values())
            self.pending.clear()
            for reply in replies:
                reply.abort()
            self.update_button.setEnabled(True)

    def update_local(self):
        if self.location:
            loc = self.location
            altitude = elevation(Observer(loc.latitude, loc.longitude, loc.altitude_m), datetime.now(timezone.utc))
            self.local_info.setText(f'{loc.name} · Lua a {altitude:.1f}° · ' +
                ('acima do horizonte' if altitude > 0 else 'abaixo do horizonte'))

    def tick(self):
        self.update_local()
        if self.enabled and self.last_hour != lunar_hour():
            self.refresh_data()

    def _get(self, key, url, handler, failed):
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(30000)
        reply = self.manager.get(request)
        self.pending[key] = reply
        generation = self.generation
        self.update_button.setEnabled(False)
        def finished():
            if generation != self.generation:
                reply.deleteLater()
                return
            self.pending.pop(key, None)
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise ValueError(reply.errorString())
                handler(bytes(reply.readAll()))
            except (ValueError, KeyError, TypeError, OverflowError):
                failed()
            finally:
                reply.deleteLater()
                self.update_button.setEnabled(not self.pending)
        deadline = QTimer(reply)
        deadline.setSingleShot(True)
        deadline.timeout.connect(reply.abort)
        reply.finished.connect(deadline.stop)
        reply.finished.connect(finished)
        deadline.start(45000)

    def refresh_data(self):
        if self.pending:
            return
        self.update_local()
        hour = lunar_hour()
        self.status.setText('Atualizando imagem e mapa lunar…')
        self._get('metadata', LUNAR_API + hour.strftime('%Y-%m-%dT%H:00'),
            lambda data: self._metadata(json.loads(data), hour), self._failed)

    def _metadata(self, data, hour):
        preview_url, atlas_url, labels_url = lunar_sources(data, hour)
        illumination = float(data['phase'])
        age = float(data['age'])
        distance = float(data['distance'])
        diameter = float(data['diameter'])
        # Commit both images together so an old atlas never labels a new phase.
        images = {}
        def loaded(key, content):
            image = QImage.fromData(content)
            if image.isNull():
                raise ValueError('Imagem lunar inválida')
            if key in ('atlas', 'labels'):
                if image.width() != 3840 or image.height() != 2160:
                    raise ValueError('Formato do mapa lunar inesperado')
                image = image.copy(840, 0, 2160, 2160)
            images[key] = image
            if len(images) != 3:
                return
            painter = QPainter(images['atlas'])
            painter.drawImage(0, 0, images['labels'])
            painter.end()
            self.moon.image = images['preview']
            self.moon.atlas = images['atlas']
            self.moon.url = atlas_url
            self.moon.message = hour.strftime('%d/%m %H:%M UTC') + ' · Clique para ver mares e crateras'
            self.moon.update()
            self.moon.update_viewer()
            self.phase.setText(f'{lunar_phase_name(age, illumination)} · {illumination:.1f}% iluminada')
            self.details.setText(f'Idade: {age:.1f} dias · Distância: {distance:,.0f} km'.replace(',', '.') +
                f'\nDiâmetro aparente: {diameter / 60:.1f}′ · Norte para cima')
            local = hour.astimezone(ZoneInfo(self.location.timezone)) if self.location else hour
            self.status.setText(f'NASA SVS / LRO · {local:%d/%m/%Y %H:%M %Z}\nSimulação horária · nomes oficiais dos mares e crateras próximos ao terminador')
            self.last_hour = hour
        self._get('preview', preview_url, lambda content: loaded('preview', content), self._failed)
        self._get('atlas', atlas_url, lambda content: loaded('atlas', content), self._failed)
        self._get('labels', labels_url, lambda content: loaded('labels', content), self._failed)

    def _failed(self):
        self.status.setText('Falha na atualização lunar · tente Atualizar Lua' +
            (' · mantendo imagem e mapa anteriores' if not self.moon.image.isNull() else ' · imagem indisponível'))
        if self.moon.image.isNull():
            self.moon.message = 'Imagem lunar indisponível'
            self.moon.update()

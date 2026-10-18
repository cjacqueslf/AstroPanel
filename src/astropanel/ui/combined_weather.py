"""Station observations from InstaRain over Windy's geographical map."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import Qt, QTimer
from astropanel.services.instarain import InstaRainClient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QSlider, QLabel


def overlay_script(stations: list[dict]) -> str:
    """Use one Leaflet map so both layers share projection, zoom and position."""
    return """(() => {
        if (typeof L === 'undefined') return false;
        const map = window.astroInstaMap || (window.W && W.map && W.map.map);
        if (!map) return false;
        if (!map._loaded) return false;
        if (!map.getPane('astroInstaRain')) {
            map.createPane('astroInstaRain').style.zIndex = '650';
        }
        if (map._astroInstaRain) map.removeLayer(map._astroInstaRain);
        const group = L.layerGroup();
        const descriptions = ['Céu limpo', 'Parcialmente nublado', 'Nublado',
                              'Chuva fraca', 'Chuva moderada', 'Chuva forte'];
        const colours = ['#2196f3', '#64b5f6', '#9e9e9e', '#ffeb3b', '#ff9800', '#f44336'];
        const iconNames = ['Blue', 'Blue2', 'Gray', 'Yellow', 'Orange', 'Red'];
        const iconUrl = index => 'https://www.instarain.com.br/web/mapa/' + iconNames[index] + '.png';
        if (!map._astroInstaRainLegend) {
            const legend = L.control({position: 'bottomleft'});
            legend.onAdd = () => {
                const box = document.createElement('div');
                box.className = 'astro-instarain-legend';
                box.setAttribute('aria-label', 'Legenda das estações InstaRain');
                box.style.cssText = 'background:rgba(9,18,28,.94);color:#edf4fa;padding:6px 8px;'
                    + 'border-radius:5px;font:11px/1.3 Arial,sans-serif;max-width:260px;';
                const title = document.createElement('strong');
                title.textContent = 'InstaRain · condições';
                box.appendChild(title);
                const items = document.createElement('div');
                items.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:2px 9px;margin-top:3px';
                descriptions.forEach((description, index) => {
                    const row = document.createElement('div');
                    row.style.cssText = 'display:flex;align-items:center;gap:4px;white-space:nowrap';
                    const image = document.createElement('img');
                    image.src = iconUrl(index); image.alt = ''; image.width = 20; image.height = 20;
                    const text = document.createElement('span'); text.textContent = description;
                    row.appendChild(image); row.appendChild(text); items.appendChild(row);
                });
                box.appendChild(items);
                L.DomEvent.disableClickPropagation(box);
                L.DomEvent.disableScrollPropagation(box);
                return box;
            };
            map._astroInstaRainLegend = legend.addTo(map);
        }
        const number = value => typeof value === 'number' && Number.isFinite(value)
            ? value.toFixed(1) : '—';
        for (const station of STATIONS) {
            station.latitude = Number(station.latitude);
            station.longitude = Number(station.longitude);
            if (!Number.isFinite(station.latitude) || !Number.isFinite(station.longitude)
                || Math.abs(station.latitude) > 90 || Math.abs(station.longitude) > 180) continue;
            const weather = Number(station.weather);
            const category = weather <= 2 ? 0 : weather === 3 ? 1 : weather === 4 ? 2
                : weather <= 6 ? 3 : weather === 7 ? 4 : 5;
            const colour = station.online === false ? '#757575' : colours[category];
            const point = [station.latitude, station.longitude];
            const text = document.createElement('div');
            for (const line of [station.name || 'Estação InstaRain',
                'InstaRain · ' + (station.condition || descriptions[category]),
                'Temperatura: ' + number(station.temperature) + ' °C',
                'Chuva nas últimas 24 h: ' + number(station.rain24h) + ' mm',
                'Medição: ' + (station.time || 'indisponível'),
                station.online === false ? 'Estação offline' : '']) {
                if (!line) continue;
                const row = document.createElement('div'); row.textContent = line; text.appendChild(row);
            }
            const radius = Number(station.radius);
            L.circle(point, {pane: 'astroInstaRain', radius: Number.isFinite(radius) && radius > 0
                ? Math.min(radius * 1000, 100000) : 1500, color: colour,
                weight: 1, fillColor: colour, fillOpacity: 0.25})
                .bindPopup(text.cloneNode(true)).addTo(group);
            L.marker(point, {pane: 'astroInstaRain', opacity: 0.8,
                icon: L.icon({iconUrl: iconUrl(category), iconSize: [31, 31], iconAnchor: [15, 31]})})
                .bindTooltip(station.name || 'Estação InstaRain')
                .bindPopup(text).addTo(group);
        }
        map._astroInstaRain = group.addTo(map);
        map._astroInstaRainCount = STATIONS.length;
        return true;
    })()""".replace("STATIONS", json.dumps(stations, ensure_ascii=True, allow_nan=False))


class CombinedWeatherControls(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.browser = None
        self._generation = 0
        self.client = InstaRainClient(self)
        self.client.ready.connect(self._received_stations)
        self.client.failed.connect(self._station_error)
        self._timezone = ZoneInfo("UTC")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._read)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.clouds = QCheckBox("Nuvens Windy")
        self.stations = QCheckBox("Estações InstaRain")
        self.clouds.setChecked(True)
        self.stations.setChecked(True)
        self.cloud_opacity = QSlider(Qt.Orientation.Horizontal)
        self.station_opacity = QSlider(Qt.Orientation.Horizontal)
        for checkbox, slider, value in ((self.clouds, self.cloud_opacity, 65),
                                        (self.stations, self.station_opacity, 90)):
            row = QHBoxLayout()
            slider.setRange(0, 100)
            slider.setValue(value)
            slider.setToolTip("Opacidade da camada (0–100%)")
            slider.setMinimumWidth(45)
            row.addWidget(checkbox)
            row.addWidget(slider, 1)
            layout.addLayout(row)
            checkbox.toggled.connect(self.apply_opacity)
            slider.valueChanged.connect(self.apply_opacity)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.parentWidget() and self.parentWidget().height() < 320
        self.status.setWordWrap(not compact)

    def start(self, browser, profile, timezone="UTC"):
        self.stop()
        try:
            self._timezone = ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            self._timezone = ZoneInfo("UTC")
        self.browser = browser
        self.status.setText("Carregando estações InstaRain…")
        self.timer.start(2000)
        self.show()
        self._read()

    def stop(self):
        self._generation += 1
        self.client.stop()
        self.timer.stop()
        self.browser = None
        self.hide()

    def apply_opacity(self, *_):
        if not self.browser:
            return
        clouds = self.cloud_opacity.value() / 100 if self.clouds.isChecked() else 0
        stations = self.station_opacity.value() / 100 if self.stations.isChecked() else 0
        script = """(() => {
            let style = document.getElementById('astro-weather-opacity');
            if (!style) {style = document.createElement('style');
                style.id = 'astro-weather-opacity'; document.head.appendChild(style);}
            style.textContent = 'canvas.leaflet-tile {opacity: CLOUDS !important;} '
                + '.particles-layer {opacity: CLOUDS !important;}';
            const pane = window.W && W.map && W.map.map.getPane('astroInstaRain');
            if (pane) {pane.style.opacity = 'STATIONS';
                pane.style.display = STATIONS === 0 ? 'none' : '';}
        })()""".replace("CLOUDS", str(clouds)).replace("STATIONS", str(stations))
        self.browser.page().runJavaScript(script)

    def _read(self):
        if self.browser:
            self.client.refresh()

    def _station_error(self, error):
        self.status.setText('Não foi possível atualizar as estações InstaRain: '+error)
        self.timer.setInterval(30000)

    def _received_stations(self, stations):
        if not self.browser:
            return
        generation = self._generation
        def drawn(success):
            if generation != self._generation:
                return
            if not success:
                self.status.setText('Aguardando o mapa de nuvens para exibir as estações…')
                self.timer.setInterval(5000)
                return
            self.apply_opacity()
            self.timer.setInterval(90000)
            self.status.setText(f'InstaRain: {len(stations)} estações · consulta {datetime.now(self._timezone):%H:%M} · '
                                'Windy: previsão no horário selecionado no mapa')
        self.browser.page().runJavaScript(overlay_script(stations), drawn)

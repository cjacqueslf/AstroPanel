from PySide6.QtCore import QUrl, QTimer, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEngineLoadingInfo, QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QPushButton, QStackedWidget, QWidget, QVBoxLayout, QTabWidget, QSizePolicy, QHBoxLayout, QLayout

from astropanel.services.map_providers import MAP_PROVIDERS, weather_web_url
from astropanel.services.settings import default_config_path
from astropanel.ui.widgets import Card, SatelliteMapWidget
from astropanel.ui.combined_weather import CombinedWeatherControls, overlay_script
from astropanel.services.instarain import InstaRainClient
from astropanel.ui.instarain import map_html, FIT_NEAREST
from astropanel.ui.weather_ads import WeatherAdInterceptor, light_pollution_layout_script, light_pollution_observer_script


class WeatherMapPage(QWidget):
    def __init__(self, profile_factory, parent=None):
        super().__init__(parent)
        self.profile_factory = profile_factory
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(4)
        title = QLabel()
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        self.stack = QStackedWidget()
        self.stack.setMinimumHeight(30)
        self.satellite = SatelliteMapWidget()
        self.satellite.setMinimumHeight(30)
        self.stack.addWidget(self.satellite)
        self.map_heading = title
        title.setParent(self.stack)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title.setStyleSheet("background: #071019; color: white; padding: 4px 8px; border-radius: 4px;")
        title.move(8, 8)
        self.body.addWidget(self.stack, 1)
        self.combined = CombinedWeatherControls(self)
        self.body.addWidget(self.combined)
        self.browser = None
        self.web_profile = None
        self.location_timer = QTimer(self)
        self.location_timer.setInterval(1000)
        self.location_timer.timeout.connect(self._position_observer)
        self.instarain = InstaRainClient(self)
        self.instarain.ready.connect(self._stations_received)
        self.instarain.failed.connect(self._stations_failed)
        self.station_refresh = QTimer(self)
        self.station_refresh.setInterval(90000)
        self.station_refresh.timeout.connect(self.instarain.refresh)
        self._stations = None
        self._navigation_generation = 0
        self.current_url = ""
        self._source_key = None
        self.status = QLabel()
        self.status.setObjectName("locationName")
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)
        self.open_button = QPushButton("Abrir mapa no navegador")
        self.open_button.setObjectName("settingsButton")
        self.open_button.clicked.connect(self.open_browser)
        self.station_button = QPushButton("Mostrar região com estações InstaRain")
        self.station_button.setObjectName("settingsButton")
        self.station_button.clicked.connect(self.fit_stations)
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.station_button)
        self.body.addLayout(buttons)
        self.station_button.hide()
        self.status.hide()
        self.open_button.hide()

    def set_location(self, location, provider, force=False):
        key = (location, provider)
        if self._source_key == key and not force:
            return
        self._source_key = key
        self.combined.stop()
        self.instarain.stop()
        self.station_refresh.stop()
        self._stations = None
        self.location_timer.stop()
        self._navigation_generation += 1
        heading = MAP_PROVIDERS.get(provider, provider)
        if location.show_map_label:
            heading += " · " + (location.map_label or location.name)
        self.map_heading.setText(heading)
        self.map_heading.adjustSize()
        map_name = location.name
        if provider == 'light_pollution':
            map_name = (location.map_label or location.name) if location.show_map_label else ''
        url = weather_web_url(provider, location.latitude, location.longitude, map_name)
        self.current_url = url
        self.status.setVisible(bool(url))
        self.open_button.setVisible(bool(url))
        self.station_button.setVisible(provider in ("instarain", "windy_instarain"))
        if url:
            # Stop the image request before changing to a web provider.
            if self.satellite.reply:
                self.satellite.reply.abort()
            if self.browser is None:
                self.web_profile = self.profile_factory()
                self.browser = QWebEngineView()
                self.browser.setPage(QWebEnginePage(self.web_profile, self.browser))
                self.browser.page().loadingChanged.connect(self.loaded)
                self.stack.addWidget(self.browser)
            self.stack.setCurrentWidget(self.browser)
            self.status.setText("Carregando mapa online…")
            if provider == 'instarain':
                self.browser.setHtml(map_html(location), QUrl('https://www.instarain.com.br/'))
                self.instarain.refresh()
                self.station_refresh.start()
            else:
                self.browser.setUrl(QUrl(url))
            if provider == "windy_instarain":
                self.combined.start(self.browser, self.web_profile, location.timezone)
        else:
            if self.browser:
                self.browser.stop()
                self.browser.setUrl(QUrl("about:blank"))
            self.stack.setCurrentWidget(self.satellite)
            self.satellite.set_location(location, provider)
        self.map_heading.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.map_heading.setMaximumWidth(max(20, self.stack.width() - 16))
        self.map_heading.adjustSize()
        self.map_heading.raise_()

    def loaded(self, info):
        self.map_heading.raise_()
        if not self.current_url:
            return
        state = QWebEngineLoadingInfo.LoadStatus
        if info.status() == state.LoadStartedStatus:
            self.status.setText("Carregando mapa online…")
            self.status.show()
        elif info.status() == state.LoadSucceededStatus:
            self.status.hide()
            if self._source_key[1] in ('instarain', 'light_pollution'):
                self.location_timer.start(1000)
        elif info.status() == state.LoadFailedStatus and info.errorCode() != -3:
            self.status.setText("O mapa não carregou. Tente abrir no navegador.")
            self.status.show()

    def _position_observer(self):
        if self._source_key and self._source_key[1] == 'light_pollution':
            generation = self._navigation_generation
            def placed(success):
                if generation == self._navigation_generation and success:
                    self.location_timer.stop()
            self.browser.page().runJavaScript(light_pollution_observer_script(self._source_key[0]), placed)
        else:
            self._position_instarain()

    def _stations_received(self, stations):
        self._stations = stations
        self._position_instarain()

    def _stations_failed(self, error):
        self.status.setText('Não foi possível atualizar as estações InstaRain: '+error)
        self.status.show()

    def _position_instarain(self):
        if not self.browser or not self._source_key or self._source_key[1] != 'instarain':
            self.location_timer.stop()
            return
        if self._stations is None:
            return
        generation = self._navigation_generation
        def drawn(success):
            if generation != self._navigation_generation:
                return
            if success:
                self.location_timer.stop()
                self.browser.page().runJavaScript(FIT_NEAREST)
                self.status.setText(f'InstaRain · {len(self._stations)} estações')
                self.status.show()
            else:
                self.location_timer.start(1000)
        self.browser.page().runJavaScript(overlay_script(self._stations), drawn)

    def fit_stations(self):
        if not self.browser:
            return
        script = """(() => {
            if (typeof L === 'undefined') return false;
            if (window.astroInstaMap || (window.W && W.map && W.map.map)) {
                const map = window.astroInstaMap || W.map.map, points = [];
                if (!map._astroInstaRain) return false;
                map._astroInstaRain.eachLayer(layer => {
                    if (layer.getLatLng) points.push(layer.getLatLng());
                });
                if (!points.length) return false;
                map.fitBounds(L.latLngBounds(points), {padding: [35, 35], maxZoom: 9});
                return true;
            }
            if (typeof _app === 'undefined') return false;
            const component = _app.Sys1.get('mapa');
            if (!component) return false;
            let found = false;
            for (const map of component.maps.values()) {
                const points = (map.dataValue || []).filter(s => s.Publico !== false)
                    .map(s => [Number(s.Latitude), Number(s.Longitude)])
                    .filter(p => p.every(Number.isFinite));
                if (!points.length) continue;
                map.fitBounds(L.latLngBounds(points), {padding: [35, 35], maxZoom: 9});
                found = true;
            }
            return found;
        })()"""
        def fitted(success):
            self.status.setVisible(not success)
            if not success:
                self.status.setText("As estações ainda estão carregando. Tente novamente em alguns segundos.")
        self.browser.page().runJavaScript(script, fitted)

    def open_browser(self):
        if self.current_url:
            QDesktopServices.openUrl(QUrl(self.current_url))


TAB_LABELS = {
    "goes19_geocolor": "GOES GeoColor", "goes19_infrared": "GOES IR",
    "nasa_gibs_free": "NASA", "windy_clouds": "Nuvens",
    "windy_lclouds": "Baixas", "windy_mclouds": "Médias", "windy_hclouds": "Altas",
    "instarain": "InstaRain", "windy_instarain": "Combinado",
    "light_pollution": "Poluição luminosa", "ventusky": "Ventusky", "none": "Desativado",
}


class WeatherPanel(Card):
    provider_changed = Signal(str)

    def __init__(self):
        super().__init__("Meteorológico")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.findChild(QLabel, "cardTitle").hide()
        self.location = None
        self.web_profile = None
        self.pages = {}
        self.tabs = QTabWidget()
        self.tabs.setObjectName("weatherTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setMinimumWidth(0)
        self.tabs.tabBar().setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.tabs.setMinimumWidth(0)
        self.body.addWidget(self.tabs, 1)
        for provider, title in MAP_PROVIDERS.items():
            if provider == "none":
                continue
            page = WeatherMapPage(self._profile, self)
            self.pages[provider] = page
            index = self.tabs.addTab(page, TAB_LABELS[provider])
            self.tabs.setTabToolTip(index, title)
            self.tabs.tabBar().setTabData(index, provider)
        self.tabs.currentChanged.connect(self._tab_changed)

    @property
    def current_provider(self):
        return self.tabs.tabBar().tabData(self.tabs.currentIndex())

    @property
    def satellite(self):
        return self.pages[self.current_provider].satellite

    def _profile(self):
        if self.web_profile is None:
            storage = default_config_path().parent / "weather-browser"
            storage.mkdir(parents=True, exist_ok=True)
            self.web_profile = QWebEngineProfile("AstroPanelWeather", self)
            self.ad_interceptor = WeatherAdInterceptor(self.web_profile)
            self.web_profile.setUrlRequestInterceptor(self.ad_interceptor)
            self.web_profile.scripts().insert(light_pollution_layout_script())
            self.web_profile.setPersistentStoragePath(str(storage))
            self.web_profile.setCachePath(str(storage / "cache"))
            self.web_profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        return self.web_profile

    def set_location(self, location, provider, force=False):
        self.location = location
        provider = provider if provider in self.pages else "goes19_geocolor"
        index = list(self.pages).index(provider)
        previous = self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(previous)
        self._activate(force)

    def _tab_changed(self, _index):
        if self.location is None:
            return
        self._activate()
        self.provider_changed.emit(self.current_provider)

    def _activate(self, force=False):
        for provider, page in self.pages.items():
            if provider != self.current_provider:
                page.combined.timer.stop()
        page = self.pages[self.current_provider]
        page.set_location(self.location, self.current_provider, force)
        if self.current_provider == "windy_instarain" and page.combined.browser:
            if not page.combined.timer.isActive():
                page.combined.timer.start(30000)
                page.combined._read()

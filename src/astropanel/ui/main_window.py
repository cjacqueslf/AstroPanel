from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import QTimer, Qt, QEvent
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QPixmap, QKeySequence
from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                               QFrame, QMenu, QDialog, QPushButton, QScrollArea, QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget)

from astropanel.domain.models import AppSettings, PANEL_NAMES
from astropanel.services.astronomy import SunMoonInfo, calculate_sun_moon, local_sidereal_time, moon_altitude_series, calculate_moonless_windows, moonless_status, next_moonset, moonset_countdown
from astropanel.services.settings import SettingsService
from astropanel.services.planets import calculate_planet_night
from astropanel.services.startup import set_start_with_windows
from astropanel.ui.sky import SkyNowDialog
from astropanel.ui.icons import application_icon, application_icon_path
from astropanel.ui.settings_dialog import SettingsDialog
from astropanel.ui.panels_dialog import PanelsDialog
from astropanel.ui.timeline import NightTimelinePanel
from astropanel.ui.planets import PlanetVisibilityPanel
from astropanel.ui.fitted_panel import FittedPanel
from astropanel.ui.weather import WeatherPanel
from astropanel.ui.seeing import SeeingPanel
from astropanel.ui.solar import SolarObservingPanel
from astropanel.ui.lunar import LunarObservingPanel
from astropanel.ui.widgets import Card, MoonAltitudeChart, MoonPanel, SatelliteMapWidget, SunPanel, WorldMapWidget


def _time_text(value: datetime | None) -> str:
    return value.strftime("%H:%M") if value else "—"


class MainWindow(QMainWindow):
    def __init__(self, settings_service: SettingsService | None = None) -> None:
        super().__init__()
        self.settings_service = settings_service or SettingsService()
        self.settings = self.settings_service.load()
        self.setWindowTitle("AstroPanel")
        self.setWindowIcon(application_icon())
        self.resize(1080, 690)
        self.setMinimumSize(420, 330)
        self.extra_panel_dialogs = {}
        self._build_ui()
        self._build_tray()
        self._apply_settings()
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1000)
        self.map_timer = QTimer(self); self.map_timer.timeout.connect(self.refresh_map); self.map_timer.start(600_000)
        self.refresh()

    def _build_ui(self) -> None:
        root = QWidget(); self.setCentralWidget(root); layout = QVBoxLayout(root); layout.setSpacing(9)
        header = QHBoxLayout(); header.setContentsMargins(2, 0, 2, 0)
        brand_icon = QLabel(); brand_icon.setObjectName("brandIcon")
        brand_pixmap = QPixmap(application_icon_path())
        brand_icon.setPixmap(brand_pixmap.scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand_icon.setToolTip("AstroPanel")
        self.location_name = QLabel(); self.location_name.setObjectName("locationName")
        self.location_name.setMinimumWidth(0); self.location_name.setWordWrap(False)
        self.location_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        settings_button = QPushButton("⚙  Configurações"); settings_button.setObjectName("settingsButton")
        settings_button.clicked.connect(self.open_settings)
        panels_button = QPushButton("▦  Painéis"); panels_button.setObjectName("settingsButton")
        panels_button.clicked.connect(self.open_panels)
        self.other_panels_button = QPushButton("Outros Painéis")
        self.other_panels_button.setObjectName("settingsButton")
        self.other_panels_menu = QMenu(self.other_panels_button)
        self.other_panels_menu.aboutToShow.connect(self._populate_other_panels)
        self.other_panels_button.setMenu(self.other_panels_menu)
        self.sky_dialog = SkyNowDialog(self)
        self.sky_button = QPushButton("Céu agora")
        self.sky_button.setObjectName("settingsButton")
        self.sky_button.clicked.connect(lambda: self.sky_dialog.open_for(self.settings.location))
        header.addWidget(brand_icon); header.addWidget(self.location_name, 1); header.addWidget(panels_button); header.addWidget(self.other_panels_button); header.addWidget(self.sky_button); header.addWidget(settings_button)
        layout.addLayout(header)
        clocks = Card("Relógios")
        self.clocks_card = clocks
        clock_strip = QFrame(); clock_strip.setObjectName("clockStrip")
        clock_layout = QHBoxLayout(clock_strip); clock_layout.setContentsMargins(8, 8, 8, 8); clock_layout.setSpacing(0)
        self.utc_clock = self._clock("UTC"); self.local_clock = self._clock("LOCAL"); self.lst_clock = self._clock("LST")
        clock_layout.addWidget(self.utc_clock[0], 1); clock_layout.addWidget(self._clock_divider())
        clock_layout.addWidget(self.local_clock[0], 1); clock_layout.addWidget(self._clock_divider())
        clock_layout.addWidget(self.lst_clock[0], 1)
        clocks.body.addWidget(clock_strip); layout.addWidget(clocks)
        self.sun_box = SunPanel()
        self.moon_box = MoonPanel()
        self.sun_moon_content = QWidget()
        self.sun_moon_content.setObjectName("sunMoonContent")
        self.sun_moon_content.setStyleSheet("QWidget#sunMoonContent { background: transparent; }")
        self.sun_moon_content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.sun_moon_content.setAutoFillBackground(False)
        sun_moon_layout = QHBoxLayout(self.sun_moon_content)
        sun_moon_layout.setContentsMargins(0, 0, 0, 0)
        sun_moon_layout.setSpacing(8)
        sun_moon_layout.addWidget(self.sun_box, 1)
        sun_moon_layout.addWidget(self.moon_box, 1)
        self.sun_moon_panel = FittedPanel(self.sun_moon_content)
        self.moon_altitude_chart = MoonAltitudeChart()
        self.sun_box.setToolTip("Horários calculados para a localização e o fuso configurados.")
        self.moon_box.setToolTip("A iluminação representa a fração do disco lunar visível.")
        self.moonless_dialog = QDialog(self)
        self.moonless_dialog.setWindowTitle("Observação sem Lua")
        self.moonless_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.moonless_dialog.resize(520, 260)
        dialog_layout = QVBoxLayout(self.moonless_dialog)
        self.moonless_card = Card("Observação sem Lua")
        self.moonless_details = QLabel(); self.moonless_details.setWordWrap(True)
        self.moonless_status = QLabel(); self.moonless_status.setWordWrap(True)
        for label in (self.moonless_details, self.moonless_status):
            label.setObjectName("locationName")
            self.moonless_card.body.addWidget(label)
        self.moonless_card.setToolTip("Noite do meio-dia ao meio-dia seguinte. Sol abaixo de −18° e Lua abaixo de 0°. Não considera nuvens ou obstáculos no horizonte.")
        dialog_layout.addWidget(self.moonless_card)
        self.moonless_moonset = QLabel(); self.moonless_moonset.setWordWrap(True)
        self.moonless_moonset.setObjectName("locationName")
        self.moonless_card.body.addWidget(self.moonless_moonset)
        explanation = QLabel("Sol abaixo de −18° e Lua abaixo do horizonte.\nHorários no fuso do observatório.")
        explanation.setObjectName("locationName"); explanation.setWordWrap(True)
        dialog_layout.addWidget(explanation)
        close_button = QPushButton("Fechar"); close_button.setObjectName("settingsButton")
        close_button.clicked.connect(self.moonless_dialog.close)
        dialog_layout.addWidget(close_button)
        self.moon_box.moonless_button.clicked.connect(self.open_moonless)
        self.satellite_card = WeatherPanel()
        self.satellite_card.provider_changed.connect(self._weather_provider_changed)
        self.satellite = self.satellite_card.satellite
        self.daynight_card = Card("Dia e Noite")
        self.world = WorldMapWidget(self.settings.location); self.daynight_card.body.addWidget(self.world)
        self.daynight_card.embed_title(self.world)
        self.timeline_panel = NightTimelinePanel()
        self.planet_panel = PlanetVisibilityPanel()
        self.seeing_panel = SeeingPanel()
        self.solar_panel = SolarObservingPanel()
        self.lunar_panel = LunarObservingPanel()
        self._planets_key = None
        self.panels = {"sun_moon": self.sun_moon_panel,
                       "moon_altitude": FittedPanel(self.moon_altitude_chart), "weather": self.satellite_card,
                       "daynight": FittedPanel(self.daynight_card), "timeline": FittedPanel(self.timeline_panel),
                       "planets": FittedPanel(self.planet_panel), "seeing": FittedPanel(self.seeing_panel), "solar": FittedPanel(self.solar_panel),
                       "lunar": FittedPanel(self.lunar_panel)}
        self.panel_scroll = QScrollArea(); self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.panel_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.panel_container = QWidget()
        self.panel_grid = QGridLayout(self.panel_container)
        self.panel_grid.setContentsMargins(0, 0, 0, 0); self.panel_grid.setSpacing(9)
        self.panel_scroll.setWidget(self.panel_container)
        layout.addWidget(self.panel_scroll, 1)
        self.empty_panel_slots = [QWidget() for _ in range(4)]
        for slot in self.empty_panel_slots:
            slot.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._layout_key = None
        fullscreen_action = QAction("Tela cheia", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        self.addAction(fullscreen_action)
        self._update_responsive_layout()

    @staticmethod
    def _clock(title: str) -> tuple[QWidget, QLabel]:
        card = QWidget(); card.setObjectName("clockSegment")
        layout = QVBoxLayout(card); layout.setContentsMargins(8, 7, 8, 8); layout.setSpacing(2)
        label = QLabel(title); label.setObjectName("clockLabel"); value = QLabel("--:--:--"); value.setObjectName("clockValue")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter); label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label); layout.addWidget(value); return card, value

    @staticmethod
    def _clock_divider() -> QFrame:
        divider = QFrame(); divider.setObjectName("clockDivider"); divider.setFrameShape(QFrame.Shape.VLine); divider.setFrameShadow(QFrame.Shadow.Plain)
        return divider

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(application_icon(), self)
        menu = QMenu(self)
        toggle = QAction("Ocultar", self); toggle.triggered.connect(self.toggle_visibility); menu.addAction(toggle)
        settings_action = QAction("Configurações…", self); settings_action.triggered.connect(self.open_settings); menu.addAction(settings_action)
        menu.addSeparator(); quit_action = QAction("Sair", self); quit_action.triggered.connect(QApplication.quit); menu.addAction(quit_action)
        self.tray.setContextMenu(menu); self.tray.activated.connect(lambda reason: self.toggle_visibility() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _apply_settings(self) -> None:
        if bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) != self.settings.always_on_top:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.settings.always_on_top)
        self.show()
        for name, dialog in list(self.extra_panel_dialogs.items()):
            if name in self.settings.visible_panels:
                dialog.close()
        if getattr(self, "_applied_location", None) != self.settings.location:
            self._moonless_key = None
            self._moonset_key = None
            self._sunmoon_key = None
            self.world.set_location(self.settings.location)
            self._applied_location = self.settings.location
        self._update_responsive_layout()
        self.seeing_panel.set_location(self.settings.location, self._panel_is_active("seeing"))
        self.solar_panel.set_location(self.settings.location, self._panel_is_active("solar"))
        self.lunar_panel.set_location(self.settings.location, self._panel_is_active("lunar"))
        if self._panel_is_active("weather"):
            self.satellite_card.set_location(self.settings.location, self.settings.map_provider)
        self.location_name.setText(f"⌖  {self.settings.location.name}  ·  {self.settings.location.latitude:.4f}, {self.settings.location.longitude:.4f}  ·  {self.settings.location.altitude_m:.0f} m")
        if getattr(self, "_applied_red_mode", None) != self.settings.red_mode:
            QApplication.instance().setStyleSheet(self._stylesheet(self.settings.red_mode))
            self._applied_red_mode = self.settings.red_mode

    def refresh_map(self) -> None:
        if self.settings.auto_update_maps and self._panel_is_active("weather"):
            self.satellite_card.set_location(self.settings.location, self.settings.map_provider, force=True)

    def _weather_provider_changed(self, provider: str) -> None:
        self.settings = replace(self.settings, map_provider=provider)
        self.settings_service.save(self.settings)

    @staticmethod
    def _stylesheet(red: bool) -> str:
        accent = "#e35050" if red else "#7fc7e8"; foreground = "#ff8b8b" if red else "#e5f2f7"
        return f"""
        QMainWindow {{ background: #091018; color: {foreground}; }} QWidget {{ font-family: Segoe UI; }}
        #card {{ background: #101d29; border: 1px solid #243746; border-radius: 7px; }}
        #seeingSummary {{ color: {foreground}; font-size: 20px; font-weight: bold; }}
        QTableWidget#seeingForecast {{ background: #07131d; color: {foreground}; gridline-color: #294455; border: 0; }}
        QTableWidget#seeingForecast QHeaderView::section {{ background: #172b3b; color: {accent}; border: 0; padding: 4px; }}
        #cardTitle {{ color: {accent}; font-size: 11px; font-weight: 600; }}
        QTabWidget#weatherTabs::pane {{ border: 0; }}
        QTabWidget#weatherTabs QTabBar::tab {{ background: #172633; color: {foreground}; padding: 6px 9px; border: 1px solid #294354; }}
        QTabWidget#weatherTabs QTabBar::tab:selected {{ background: #294354; color: {accent}; }}
        #locationName {{ color: {foreground}; font-size: 12px; font-weight: 600; }}
        #brandIcon {{ min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; }}
        #settingsButton {{ color: {foreground}; background: #172b3b; border: 1px solid #3f6278; border-radius: 6px; padding: 6px 10px; font-weight: 600; }}
        #settingsButton:hover {{ border-color: {accent}; background: #203e52; }}
        #clockStrip {{ background: #07131d; border: 1px solid #294455; border-radius: 8px; }}
        #clockSegment {{ background: transparent; }}
        #clockDivider {{ color: #294455; background: #294455; max-width: 1px; margin: 5px 0; }}
        #clockLabel {{ color: {accent}; font-size: 11px; font-weight: 650; }}
        #clockValue {{ color: {foreground}; font-size: 31px; font-weight: 650; }}
        #clockValue[compact="true"] {{ font-size: 21px; }}
        #clockLabel[compact="true"] {{ font-size: 10px; }}
        #dataBox {{ background: #0a1620; border: 1px solid #294354; border-radius: 6px; }}
        #dataBox:hover {{ border: 1px solid {accent}; background: #112534; }}
        #sunPanel {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffbd52, stop:1 #ff981f); border: 1px solid #ffd17c; border-radius: 14px; color: #ffffff; }}
        #sunPanelIcon {{ background: rgba(255,255,255,0.19); border: 1px solid rgba(255,255,255,0.45); border-radius: 10px; font-size: 25px; min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px; }}
        #sunPanelTitle {{ color: #ffffff; font-size: 12px; font-weight: 800; letter-spacing: 1px; }}
        #sunPanelTitleLine {{ background: rgba(255,255,255,0.72); border: none; }}
        #sunPanelPill {{ color: #ffffff; background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.52); border-radius: 13px; padding: 5px 10px; font-size: 11px; font-weight: 700; }}
        #sunEventIcon {{ color: #ffffff; background: rgba(255,255,255,0.18); border-radius: 18px; font-size: 19px; min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px; }}
        #sunEventTime {{ color: #ffffff; font-size: 25px; font-weight: 800; }}
        #sunEventLabel {{ color: #ffffff; font-size: 11px; font-weight: 700; }}
        #sunPanelFooter {{ background: rgba(242,132,26,0.34); border: 1px solid rgba(255,255,255,0.35); border-radius: 9px; }}
        #sunPanelSmallLabel {{ color: rgba(255,255,255,0.78); font-size: 10px; font-weight: 700; letter-spacing: .5px; }}
        #sunPanelNightValue, #sunPanelWindowValue {{ color: #ffffff; font-size: 15px; font-weight: 800; }}
        #sunPanelStatus {{ color: #ffffff; border-top: 1px solid rgba(255,255,255,0.25); padding-top: 4px; font-size: 11px; }}
        #moonPanel {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4b5f75, stop:1 #293a4c); border: 1px solid #6e8da8; border-radius: 14px; color: #ffffff; }}
        #moonPanelIcon {{ color: #dcecff; background: rgba(210,231,255,0.15); border: 1px solid rgba(210,231,255,0.48); border-radius: 10px; font-size: 24px; min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px; }}
        #moonPanelTitle {{ color: #ffffff; font-size: 12px; font-weight: 800; letter-spacing: 1px; }} #moonPanelSubtitle {{ color: #d9e7f2; font-size: 11px; }}
        #moonEventRow {{ background: rgba(12,27,42,0.38); border: 1px solid rgba(208,229,250,0.16); border-radius: 7px; }}
        #moonEventLabel {{ color: #ffffff; font-size: 10px; font-weight: 700; }} #moonEventValue {{ color: #ffffff; font-size: 18px; font-weight: 800; }}
        #moonPanelDetail {{ color: #dceafa; font-size: 10px; font-weight: 700; }}
        #moonPhases {{ background: rgba(12,27,42,0.54); border: 1px solid rgba(208,229,250,0.26); border-radius: 8px; }}
        #moonPhasesTitle {{ color: #dceafa; font-size: 10px; font-weight: 700; letter-spacing: .5px; }}
        #moonPhaseGlyph {{ color: #e2effd; font-size: 20px; }} #moonPhaseDate {{ color: #c5d6e8; font-size: 9px; font-weight: 600; }}
        #moonAltitudeChart {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3f5870, stop:1 #24394f); border: 1px solid #6e8da8; border-radius: 14px; }}
        #mapPlaceholder {{ color: #9cb2bf; background: #071019; border: 1px dashed #385061; }}
        QCheckBox {{ color: {foreground}; spacing: 8px; padding: 6px; }}
        QDialog {{ background: #101923; color: {foreground}; }}
        QDialog QWidget {{ background: #101923; color: {foreground}; }}
        QDialog QTabWidget::pane {{ border: 1px solid #294354; background: #101923; }}
        QDialog QTabBar::tab {{ background: #172633; color: {foreground}; padding: 8px 12px; }}
        QDialog QTabBar::tab:selected {{ background: #294354; color: {foreground}; }}
        QDialog QCheckBox {{ color: {foreground}; background: transparent; spacing: 8px; padding: 6px; }}
        QDialog QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {accent}; border-radius: 3px; background: #172633; }}
        QDialog QCheckBox::indicator:checked {{ background: {accent}; }}
        QDialog QLineEdit, QDialog QComboBox, QDialog QDoubleSpinBox {{ background: #172633; color: {foreground}; padding: 5px; }}
        QDialog QPushButton {{ background: #172633; color: {foreground}; padding: 6px 12px; border: 1px solid #3f6278; border-radius: 4px; }}
        """

    def refresh(self) -> None:
        now_utc = datetime.now(timezone.utc)
        try:
            local_now = now_utc.astimezone(ZoneInfo(self.settings.location.timezone))
        except Exception:
            local_now = now_utc
        self.utc_clock[1].setText(now_utc.strftime("%H:%M:%S"))
        self.local_clock[0].findChild(QLabel, "clockLabel").setText("LOCAL" if self.width() < 680 else f"LOCAL · {self.settings.location.timezone}")
        self.local_clock[1].setText(local_now.strftime("%H:%M:%S"))
        self.lst_clock[1].setText(local_sidereal_time(self.settings.location, now_utc))
        chart_day = local_now.date() if local_now.hour >= 12 else (local_now - timedelta(days=1)).date()
        sunmoon_key = (self.settings.location, local_now.date(), chart_day)
        if self._sunmoon_key != sunmoon_key:
            self._sunmoon_key = sunmoon_key
            self._sunmoon = calculate_sun_moon(self.settings.location, local_now.date())
            chart_day = local_now.date() if local_now.hour >= 12 else (local_now - timedelta(days=1)).date()
            self._moon_altitudes = moon_altitude_series(self.settings.location, chart_day)
            self._render_sunmoon(self._sunmoon)
        moonset_key = (self.settings.location, local_now.date())
        if self._moonset_key != moonset_key or (self._next_moonset and now_utc >= self._next_moonset.astimezone(timezone.utc)):
            self._next_moonset = next_moonset(self.settings.location, now_utc)
            self._moonset_key = moonset_key
        countdown = moonset_countdown(self._next_moonset, now_utc)
        self.moon_box.set_countdown.setText(countdown)
        event_text = self._next_moonset.strftime("%d/%m/%Y %H:%M") if self._next_moonset else "—"
        self.moonless_moonset.setText(f"{countdown}\nPróximo pôr da Lua: {event_text}")
        night_day = local_now.date() if local_now.hour >= 12 else (local_now - timedelta(days=1)).date()
        key = (self.settings.location, night_day)
        if self._moonless_key != key:
            self._moonless_windows = calculate_moonless_windows(self.settings.location, night_day)
            self._moonless_key = key
            self.timeline_panel.set_night(self.settings.location, night_day, self._moon_altitudes, self._moonless_windows)
            intervals = []
            for window in self._moonless_windows:
                minutes = round(window.duration.total_seconds() / 60)
                intervals.append(f"{window.start:%d/%m %H:%M} → {window.end:%d/%m %H:%M} ({minutes // 60}h {minutes % 60:02}min)")
            total = round(sum(w.duration.total_seconds() for w in self._moonless_windows) / 60)
            details = " · ".join(intervals) if intervals else "Nenhum intervalo com noite astronômica e Lua abaixo do horizonte."
            self.moonless_details.setText(f"Noite de {night_day:%d/%m/%Y} · Total: {total // 60}h {total % 60:02}min\n{details}")
        self.moonless_status.setText(moonless_status(self._moonless_windows, now_utc))
        self.moon_altitude_chart.set_current_hour(local_now.hour + local_now.minute / 60 + local_now.second / 3600)
        self.timeline_panel.set_now(now_utc, self.settings.red_mode)
        if self._panel_is_active("planets"):
            if self._planets_key != key:
                planet_night = calculate_planet_night(self.settings.location, night_day)
                self.planet_panel.set_night(planet_night, self.settings.location, night_day)
                self._planets_key = key
            self.planet_panel.set_now(now_utc, self.settings.red_mode)
        map_minute = now_utc.replace(second=0, microsecond=0)
        if self.settings.auto_update_maps and self._panel_is_active("daynight") and getattr(self, "_world_minute", None) != map_minute:
            self.world.update()
            self._world_minute = map_minute

    def _render_sunmoon(self, info: SunMoonInfo) -> None:
        night = "Não existe noite astronômica nesta data/local." if info.astronomical_night is None else f"{int(info.astronomical_night.total_seconds() // 3600)}h {int(info.astronomical_night.total_seconds() % 3600 // 60):02}min"
        daylight = "—"
        if info.sunrise and info.sunset:
            span = info.sunset - info.sunrise
            daylight = f"{int(span.total_seconds() // 3600)}h {int(span.total_seconds() % 3600 // 60):02}min"
        self.sun_box.set_values(
            _time_text(info.sunrise), _time_text(info.solar_noon), _time_text(info.sunset), daylight,
            night, f"{_time_text(info.astro_dusk)} → {_time_text(info.astro_dawn)}",
        )
        phase_name = "Nova" if info.illumination_percent < 8 else "Cheia" if info.illumination_percent > 92 else "Crescente / minguante"
        self.moon_box.set_values(
            _time_text(info.moonrise), _time_text(info.moonset), f"{info.illumination_percent:.0f}%",
            phase_name, info.moon_phase_days, info.next_moon_phases,
        )
        self.moon_altitude_chart.set_values(
            self._moon_altitudes,
            (info.astro_dawn, info.nautical_dawn, info.civil_dawn, info.sunrise,
             info.sunset, info.civil_dusk, info.nautical_dusk, info.astro_dusk),
        )

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._update_responsive_layout()

    def _toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._update_responsive_layout)

    def _update_responsive_layout(self) -> None:
        if not hasattr(self, "panel_grid"):
            return
        compact = self.width() < 680
        self.location_name.setVisible(not compact)
        for widget, value in (self.utc_clock, self.local_clock, self.lst_clock):
            for label in (value, widget.findChild(QLabel, "clockLabel")):
                if label.property("compact") != compact:
                    label.setProperty("compact", compact)
                    label.style().unpolish(label); label.style().polish(label)
        selected = tuple(name for name in self.panels if name in self.settings.visible_panels)
        key = selected
        if self._layout_key == key:
            return
        self._layout_key = key
        self.panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        while self.panel_grid.count():
            self.panel_grid.takeAt(0)
        for name, panel in self.panels.items():
            if name not in self.extra_panel_dialogs:
                panel.setVisible(name in selected)
        for index in range(4):
            empty = self.empty_panel_slots[index]
            empty.setVisible(index >= len(selected))
            panel = self.panels[selected[index]] if index < len(selected) else empty
            self.panel_grid.addWidget(panel, index // 2, index % 2)
        for index in range(2):
            self.panel_grid.setRowStretch(index, 1)
            self.panel_grid.setColumnStretch(index, 1)
        self.panel_grid.activate()

    def _panel_is_active(self, name: str) -> bool:
        return name in self.settings.visible_panels or name in self.extra_panel_dialogs

    def _populate_other_panels(self) -> None:
        self.other_panels_menu.clear()
        for name, title in PANEL_NAMES.items():
            if name not in self.settings.visible_panels:
                action = self.other_panels_menu.addAction(title)
                action.triggered.connect(lambda checked=False, key=name: self.open_other_panel(key))

    def open_other_panel(self, name: str) -> None:
        if name not in self.panels or name in self.settings.visible_panels:
            return
        dialog = self.extra_panel_dialogs.get(name)
        if dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle(f"AstroPanel — {PANEL_NAMES[name]}")
            dialog.resize(max(420, self.width() - 120), max(330, self.height() - 120))
            dialog.setMinimumSize(360, 260)
            layout = QVBoxLayout(dialog)
            layout.addWidget(self.panels[name], 1)
            close_button = QPushButton("Fechar")
            close_button.setObjectName("settingsButton")
            close_button.clicked.connect(dialog.close)
            layout.addWidget(close_button)
            self.extra_panel_dialogs[name] = dialog
            dialog.finished.connect(lambda result, key=name: self._close_other_panel(key))
            self.panels[name].show()
            self._apply_settings()
            self.refresh()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _close_other_panel(self, name: str) -> None:
        dialog = self.extra_panel_dialogs.pop(name, None)
        if dialog is None:
            return
        panel = self.panels[name]
        dialog.layout().removeWidget(panel)
        panel.hide()
        panel.setParent(self.panel_container)
        dialog.deleteLater()
        self._layout_key = None
        self._apply_settings()
        self.refresh()

    def open_panels(self) -> None:
        dialog = PanelsDialog(self.settings.visible_panels, self)
        if dialog.exec():
            self.settings = replace(self.settings, visible_panels=dialog.selected_panels())
            self.settings_service.save(self.settings)
            self._apply_settings()
            self.refresh()

    def open_moonless(self) -> None:
        self.refresh()
        self.moonless_dialog.show()
        self.moonless_dialog.raise_()
        self.moonless_dialog.activateWindow()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.result_settings()
            self.settings_service.save(self.settings)
            set_start_with_windows(self.settings.start_with_windows)
            self._apply_settings(); self.refresh()

    def toggle_visibility(self) -> None:
        if self.isVisible(): self.hide()
        else: self.showNormal(); self.raise_(); self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore(); self.hide()

import itertools
import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QSlider

from astropanel.domain.models import AppSettings, PANEL_NAMES
from astropanel.services.settings import SettingsService
from astropanel.ui.panels_dialog import PanelsDialog
from astropanel.ui.main_window import MainWindow
from astropanel.ui.widgets import SatelliteMapWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_panel_preferences_roundtrip_and_legacy_migration(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    original = AppSettings(visible_panels=["sun_moon", "timeline"])
    service.save(original)
    assert service.load().visible_panels == ["sun_moon", "timeline"]
    service.path.write_text('{"show_sun_moon": false, "show_satellite_map": true, "show_day_night_map": false}')
    assert service.load().visible_panels == ["weather"]
    service.save(AppSettings(visible_panels=[]))
    assert service.load().visible_panels == []
    with pytest.raises(ValueError):
        AppSettings(visible_panels=list(PANEL_NAMES))


def test_manager_limit_and_replacement(app):
    dialog = PanelsDialog(list(PANEL_NAMES)[:4])
    assert len(dialog.checkboxes) == len(PANEL_NAMES)
    assert not dialog.checkboxes["planets"].isEnabled()
    assert not dialog.checkboxes["timeline"].isEnabled()
    dialog.checkboxes["sun_moon"].setChecked(False)
    assert dialog.checkboxes["timeline"].isEnabled()
    dialog.checkboxes["timeline"].setChecked(True)
    assert len(dialog.selected_panels()) == 4
    assert not dialog.checkboxes["sun_moon"].isEnabled()
    dialog.close()


def test_all_selections_keep_four_equal_slots(app, tmp_path, monkeypatch):
    from astropanel.ui.weather import WeatherMapPage
    monkeypatch.setattr(WeatherMapPage, "set_location", lambda *args, **kwargs: None)
    service = SettingsService(tmp_path / "settings.json")
    window = MainWindow(service)
    window.timer.stop()
    window.map_timer.stop()
    window.show()
    try:
        for width, height in ((800, 600), (1280, 720), (1920, 1080)):
            window.resize(width, height)
            for count in range(5):
                for selected in itertools.combinations(PANEL_NAMES, count):
                    window.settings = replace(window.settings, visible_panels=list(selected))
                    window._update_responsive_layout()
                    for _ in range(3):
                        app.processEvents()
                    assert window.panel_grid.count() == 4
                    assert {name for name, panel in window.panels.items() if not panel.isHidden()} == set(selected)
                    viewport = window.panel_scroll.viewport().rect()
                    for index in range(count):
                        row, column, row_span, column_span = window.panel_grid.getItemPosition(index)
                        assert (row, column, row_span, column_span) == (index // 2, index % 2, 1, 1)
                        panel = window.panel_grid.itemAt(index).widget()
                        assert abs(panel.width() - (viewport.width() - 9) / 2) <= 1
                        assert abs(panel.height() - (viewport.height() - 9) / 2) <= 1
                        assert viewport.contains(panel.geometry())
                    assert window.panel_scroll.verticalScrollBar().maximum() == 0
                    assert window.panel_scroll.horizontalScrollBar().maximum() == 0
    finally:
        window.tray.hide()
        window.hide()


def test_timeline_uses_next_morning_and_dst_span(app):
    from datetime import date
    from astropanel.domain.models import ObservatoryLocation
    from astropanel.services.astronomy import moon_altitude_series, calculate_moonless_windows
    from astropanel.ui.timeline import NightTimelinePanel
    location = ObservatoryLocation("New York", 40.7, -74, 0, "America/New_York")
    day = date(2026, 10, 31)
    panel = NightTimelinePanel()
    panel.set_night(location, day, moon_altitude_series(location, day), calculate_moonless_windows(location, day))
    assert (panel.chart.end - panel.chart.start).total_seconds() == 25 * 3600
    assert "01/11" in panel.events.text()
    assert len(panel.chart.lunar) == 97


def test_preference_changes_do_not_reload_map_or_reset_astronomy(app, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(SatelliteMapWidget, "set_location", lambda *args: calls.append(args))
    service = SettingsService(tmp_path / "settings.json")
    service.save(AppSettings(auto_update_maps=False))
    window = MainWindow(service)
    window.timer.stop()
    window.map_timer.stop()
    try:
        old_key = window._sunmoon_key
        assert len(calls) == 1
        window.settings = replace(window.settings, red_mode=True, visible_panels=["weather", "sun_moon"])
        window._apply_settings()
        window.refresh()
        assert len(calls) == 1
        assert window._sunmoon_key == old_key
        window.satellite_card.set_location(window.settings.location, window.settings.map_provider, force=True)
        assert len(calls) == 2
        window.settings = replace(window.settings, location=replace(window.settings.location, latitude=-20))
        window._apply_settings()
        window.refresh()
        assert len(calls) == 3
        assert window._sunmoon_key != old_key
    finally:
        window.tray.hide()
        window.hide()

def test_sun_moon_are_one_panel_with_original_backgrounds(app, tmp_path, monkeypatch):
    from astropanel.ui.weather import WeatherMapPage
    monkeypatch.setattr(WeatherMapPage, "set_location", lambda *args, **kwargs: None)
    window = MainWindow(SettingsService(tmp_path / "combined.json"))
    window.timer.stop()
    window.map_timer.stop()
    try:
        assert "sun" not in window.panels and "moon" not in window.panels
        assert window.panels["sun_moon"].content is window.sun_moon_content
        assert window.sun_box.parentWidget() is window.sun_moon_content
        assert window.moon_box.parentWidget() is window.sun_moon_content
        assert window.sun_box.objectName() == "sunPanel"
        assert window.moon_box.objectName() == "moonPanel"
        assert window.sun_box.styleSheet() == window.moon_box.styleSheet() == ""
        window.sun_moon_panel.resize(360, 200)
        window.sun_moon_panel.fit_content()
        assert window.sun_moon_panel.horizontalScrollBar().maximum() == 0
        assert window.sun_moon_panel.verticalScrollBar().maximum() == 0
    finally:
        window.tray.hide()
        window.hide()


def test_legacy_panel_selection_migrates_without_losing_location(tmp_path):
    import json
    service = SettingsService(tmp_path / "legacy.json")
    service.path.write_text(json.dumps({"location": {"name": "Observatorio", "latitude": 12},
                                       "visible_panels": ["sun", "moon", "weather", "timeline", "planets"]}))
    settings = service.load()
    assert settings.visible_panels == ["sun_moon", "weather", "timeline", "planets"]
    assert settings.location.name == "Observatorio"
    assert settings.location.latitude == 12


def test_combined_map_controls_fit_in_one_quadrant(app, tmp_path, monkeypatch):
    from astropanel.ui.weather import WeatherMapPage
    monkeypatch.setattr(WeatherMapPage, "set_location", lambda *args, **kwargs: None)
    service = SettingsService(tmp_path / "combined-fit.json")
    service.save(AppSettings(map_provider="windy_instarain", auto_update_maps=False))
    window = MainWindow(service)
    window.timer.stop()
    window.map_timer.stop()
    page = window.satellite_card.pages["windy_instarain"]
    page.combined.show()
    page.open_button.show()
    page.station_button.show()
    window.show()
    try:
        window.resize(1280, 720)
        for _ in range(4):
            app.processEvents()
        assert window.panel_scroll.verticalScrollBar().maximum() == 0
        assert window.panel_scroll.horizontalScrollBar().maximum() == 0
        assert page.combined.geometry().bottom() < page.height()
    finally:
        window.tray.hide()
        window.hide()


def test_other_panels_menu_and_window_lifecycle(app, tmp_path, monkeypatch):
    from astropanel.ui.weather import WeatherMapPage
    monkeypatch.setattr(WeatherMapPage, "set_location", lambda *args, **kwargs: None)
    window = MainWindow(SettingsService(tmp_path / "extra.json"))
    window.timer.stop()
    window.map_timer.stop()
    try:
        selected = list(window.settings.visible_panels)
        window._populate_other_panels()
        extras = [name for name in PANEL_NAMES if name not in selected]
        assert [action.text() for action in window.other_panels_menu.actions()] == [PANEL_NAMES[name] for name in extras]
        name = extras[0]
        window.other_panels_menu.actions()[0].trigger()
        dialog = window.extra_panel_dialogs[name]
        app.processEvents()
        assert dialog.isVisible()
        assert window.panels[name].parentWidget() is dialog
        assert window._panel_is_active(name)
        assert window.settings.visible_panels == selected
        assert window.panel_grid.count() == 4
        window.open_other_panel(name)
        assert window.extra_panel_dialogs[name] is dialog
        window._layout_key = None
        window._update_responsive_layout()
        assert window.panels[name].isVisible()
        dialog.close()
        assert name not in window.extra_panel_dialogs
        assert window.panels[name].isHidden()
        assert window.panels[name].parentWidget() is window.panel_container
        window.open_other_panel(name)
        window.settings = replace(window.settings, visible_panels=[name])
        window._apply_settings()
        assert name not in window.extra_panel_dialogs
        assert window.panel_grid.itemAt(0).widget() is window.panels[name]
        assert window.panels[name].isVisible()
    finally:
        for dialog in list(window.extra_panel_dialogs.values()):
            dialog.close()
        window.tray.hide()
        window.hide()

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from astropanel.domain.models import ObservatoryLocation
from astropanel.services.map_providers import MAP_PROVIDERS
from astropanel.ui.weather import WeatherPanel, WeatherMapPage


def test_tabs_select_maps_lazily_and_update_observer(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(WeatherMapPage, "set_location",
                        lambda self, location, provider, force=False: calls.append((location, provider, force)))
    panel = WeatherPanel()
    assert panel.tabs.count() == len(MAP_PROVIDERS) - 1
    assert all(page.browser is None for page in panel.pages.values())
    selected = []
    panel.provider_changed.connect(selected.append)
    bh = ObservatoryLocation("BH", -19.9167, -43.9345)
    panel.set_location(bh, "windy_clouds")
    assert selected == []  # Applying settings must not save them again.
    panel.tabs.setCurrentIndex(list(panel.pages).index("instarain"))
    assert selected == ["instarain"]
    assert calls[-1] == (bh, "instarain", False)
    sp = ObservatoryLocation("SP", -23.55, -46.63)
    panel.set_location(sp, "instarain", force=True)
    panel.tabs.setCurrentIndex(list(panel.pages).index("goes19_infrared"))
    assert calls[-1] == (sp, "goes19_infrared", False)
    assert panel.tabs.usesScrollButtons()
    panel.close()


def test_tab_choice_is_saved_as_startup_map(tmp_path):
    from astropanel.domain.models import AppSettings
    from astropanel.services.settings import SettingsService
    from astropanel.ui.main_window import MainWindow

    class WindowState:
        settings = AppSettings()
        settings_service = SettingsService(tmp_path / "settings.json")

    state = WindowState()
    MainWindow._weather_provider_changed(state, "light_pollution")
    assert state.settings_service.load().map_provider == "light_pollution"

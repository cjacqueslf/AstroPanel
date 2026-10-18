from astropanel.domain.models import AppSettings, ObservatoryLocation
from astropanel.services.settings import SettingsService


def test_settings_round_trip(tmp_path) -> None:
    service = SettingsService(tmp_path / "settings.json")
    original = AppSettings(location=ObservatoryLocation("Teste", 10, 20, 30, "UTC"), red_mode=True)
    service.save(original)
    loaded = service.load()
    assert loaded.location == original.location
    assert loaded.red_mode is True


def test_removed_windy_layers_migrate_to_clouds(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    for provider in ("windy_rain", "windy_wind"):
        service.save(AppSettings(map_provider=provider))
        assert service.load().map_provider == "windy_clouds"

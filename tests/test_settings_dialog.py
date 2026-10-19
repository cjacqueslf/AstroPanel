import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from astropanel.domain.models import AppSettings
from astropanel.ui.settings_dialog import SettingsDialog


def test_reselecting_saved_location_restores_fields_and_saves_selection(tmp_path):
    from astropanel.domain.models import ObservatoryLocation
    from astropanel.services.settings import SettingsService
    app = QApplication.instance() or QApplication([])
    casa = ObservatoryLocation(name='Casa', latitude=-19.92, longitude=-43.93)
    campo = ObservatoryLocation(name='Campo', latitude=-7.11, longitude=-34.861)
    dialog = SettingsDialog(AppSettings(location=casa, saved_locations=[casa, campo]))
    dialog.name.setText('Rascunho')
    dialog.locations.activated.emit(1)
    assert dialog.name.text() == 'Casa'
    dialog.locations.setCurrentIndex(2)
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    service = SettingsService(tmp_path / 'settings.json')
    service.save(dialog.result_settings())
    assert service.load().location == campo
    assert service.load().saved_locations == [casa, campo]


def test_saved_locations_and_labels(tmp_path):
    from astropanel.services.settings import SettingsService
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(AppSettings(map_provider="windy_clouds", visible_panels=["weather"]))
    assert all(dialog.tabs.tabText(i) != "Mapas/API" for i in range(dialog.tabs.count()))
    dialog.name.setText("Casa")
    dialog.map_label.setText("Observatorio")
    dialog._add_location()
    dialog.name.setText("Campo")
    dialog.latitude.setValue(-20)
    dialog.show_map_label.setChecked(False)
    dialog._add_location()
    dialog.locations.setCurrentIndex(1)
    assert dialog.name.text() == "Casa"
    assert dialog.map_label.text() == "Observatorio"
    assert dialog.show_map_label.isChecked()
    service = SettingsService(tmp_path / "settings.json")
    service.save(dialog.result_settings())
    saved = service.load()
    assert len(saved.saved_locations) == 2
    assert saved.location.name == "Casa"
    assert saved.saved_locations[1].show_map_label is False
    assert saved.map_provider == "windy_clouds"
    assert saved.visible_panels == ["weather"]
    dialog.locations.setCurrentIndex(2)
    dialog._remove_location()
    assert len(dialog.result_settings().saved_locations) == 1
    dialog.close()


def test_new_location_adds_without_replacing_existing_and_rename_updates_selected(tmp_path):
    from astropanel.domain.models import ObservatoryLocation
    from astropanel.services.settings import SettingsService
    app = QApplication.instance() or QApplication([])
    casa = ObservatoryLocation(name='Casa', map_label='Observatório de casa')
    dialog = SettingsDialog(AppSettings(location=casa, saved_locations=[casa]))
    assert dialog.locations.currentIndex() == 1
    dialog.new_location_button.click()
    assert dialog.locations.currentIndex() == -1
    assert not dialog.name.text()
    assert not dialog.update_location_button.isEnabled()
    dialog.name.setText('Campo')
    dialog.latitude.setValue(-20)
    dialog.add_location_button.click()
    assert len(dialog.saved_locations) == 2
    assert dialog.saved_locations[0] == casa
    dialog.name.setText('Sítio')
    dialog.update_location_button.click()
    assert len(dialog.saved_locations) == 2
    assert dialog.saved_locations[1].name == 'Sítio'
    service = SettingsService(tmp_path / 'places.json')
    service.save(dialog.result_settings())
    assert [loc.name for loc in service.load().saved_locations] == ['Casa', 'Sítio']
    assert service.load().location.name == 'Sítio'
    dialog.close()


def test_duplicate_location_is_not_overwritten_and_cancel_preserves_settings():
    from astropanel.domain.models import ObservatoryLocation
    app = QApplication.instance() or QApplication([])
    casa = ObservatoryLocation(name='Casa')
    settings = AppSettings(location=casa, saved_locations=[casa])
    dialog = SettingsDialog(settings)
    dialog.new_location_button.click()
    dialog.name.setText('casa')
    dialog.latitude.setValue(-10)
    dialog.add_location_button.click()
    assert dialog.saved_locations == [casa]
    assert 'Já existe' in dialog.location_feedback.text()
    dialog.name.setText('Campo')
    dialog.add_location_button.click()
    dialog.reject()
    assert settings.saved_locations == [casa]
    assert settings.location == casa


def test_about_identifies_app_and_opens_packaged_manual(monkeypatch):
    from pathlib import Path
    from PySide6.QtWidgets import QLabel
    from astropanel import __version__
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(AppSettings())
    index = next(i for i in range(dialog.tabs.count()) if dialog.tabs.tabText(i) == 'Sobre')
    labels = [label.text() for label in dialog.tabs.widget(index).findChildren(QLabel)]
    assert 'AstroPanel' in labels
    assert __version__ in labels
    assert any('Cristóvão Jacques' in text for text in labels)
    urls = []
    monkeypatch.setattr('astropanel.ui.settings_dialog.QDesktopServices.openUrl', lambda url: urls.append(url) or True)
    dialog.manual_button.click()
    assert Path(urls[0].toLocalFile()).is_file()
    assert 'Cadastrar e selecionar locais' in Path(urls[0].toLocalFile()).read_text(encoding='utf-8-sig')
    dialog.close()


def test_new_draft_cannot_overwrite_existing_location_on_save():
    from astropanel.domain.models import ObservatoryLocation
    app = QApplication.instance() or QApplication([])
    casa = ObservatoryLocation(name='Casa')
    dialog = SettingsDialog(AppSettings(location=casa, saved_locations=[casa]))
    dialog.new_location_button.click()
    dialog.name.setText('Casa')
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.saved_locations == [casa]
    assert 'Já existe' in dialog.location_feedback.text()
    dialog.close()

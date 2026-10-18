import pytest
from PySide6.QtWidgets import QApplication
from astropanel.services.updates import parse_release, RELEASES_URL


def release(tag='v0.1.0'):
    return {'tag_name':tag, 'html_url':RELEASES_URL+'/tag/'+tag, 'draft':False, 'prerelease':False}


def test_release_comparison_is_numeric_and_accepts_current_version():
    assert not parse_release(release(), '0.1.0').newer
    assert parse_release(release('v0.10.0'), '0.9.0').newer
    assert not parse_release(release('v0.1.0'), '0.2.0').newer


@pytest.mark.parametrize('payload', [None, {}, {**release(), 'draft':True},
    {**release(), 'prerelease':True}, release('v0.2.0-beta'),
    {**release(), 'html_url':'https://example.com/releases/v0.1.0'}])
def test_invalid_release_is_not_reported_as_current(payload):
    with pytest.raises(ValueError):
        parse_release(payload)


def test_about_update_success_and_failure_reenable_button(monkeypatch):
    from astropanel.domain.models import AppSettings
    from astropanel.ui.settings_dialog import SettingsDialog
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(AppSettings())
    monkeypatch.setattr('astropanel.ui.settings_dialog.PRIVATE_CHANNEL', False)
    calls=[]
    monkeypatch.setattr(dialog.update_checker, 'check', lambda: calls.append(True))
    dialog.updates_button.click()
    assert calls == [True]
    assert not dialog.updates_button.isEnabled()
    dialog._update_checked(parse_release(release('v0.2.0')))
    assert dialog.updates_button.isEnabled()
    assert 'Nova versão disponível: 0.2.0' in dialog.update_status.text()
    dialog._update_failed('Falha de conexão')
    assert dialog.updates_button.isEnabled()
    assert dialog.update_status.text() == 'Falha de conexão'
    dialog.close()


def test_private_channel_opens_authenticated_browser_page(monkeypatch):
    from astropanel.domain.models import AppSettings
    from astropanel.ui.settings_dialog import SettingsDialog
    app = QApplication.instance() or QApplication([])
    urls=[]
    monkeypatch.setattr('astropanel.ui.settings_dialog.PRIVATE_CHANNEL', True)
    monkeypatch.setattr('astropanel.ui.settings_dialog.QDesktopServices.openUrl', lambda url: urls.append(url.toString()) or True)
    dialog = SettingsDialog(AppSettings())
    dialog.updates_button.click()
    assert urls == [RELEASES_URL]
    assert 'conta autorizada' in dialog.update_status.text()
    assert dialog.updates_button.isEnabled()
    dialog.close()

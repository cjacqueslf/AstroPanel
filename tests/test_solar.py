import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import datetime, timezone
import pytest
from PySide6.QtWidgets import QApplication, QPushButton
from astropanel.services.solar import latest_gong_link, gong_time, latest_record, region_summary, observation_stamp, gong_metadata_path
from astropanel.domain.models import AppSettings, ObservatoryLocation
from astropanel.ui.solar import SolarObservingPanel
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from astropanel.ui.fitted_panel import FittedPanel


def test_source_selection_and_dates():
    assert gong_metadata_path('<response><latestImage>/HA/hav/202610/20261012/20261012174922Th.jpg</latestImage></response>').endswith('Th.jpg')
    with pytest.raises(ValueError):
        gong_metadata_path('<response><latestImage>https://example.com/image.jpg</latestImage></response>')
    with pytest.raises(ValueError):
        gong_metadata_path('not xml')
    html = '<a href="20261012200034Ch.jpg">x</a><a href="20261012210034Lh.jpg">x</a><a href="20261012220034Zh.jpg">test</a>'
    assert latest_gong_link(html, 'image') == '20261012210034Lh.jpg'
    assert gong_time('20261012210034Lh.jpg').tzinfo == timezone.utc
    with pytest.raises(ValueError):
        latest_gong_link('<a href="https://other/image.jpg">bad</a>', 'image')
    rows = [dict(time_tag='2026-10-12', flux=123), dict(time_tag='2026-10-01', flux=90)]
    assert latest_record(rows)['flux'] == 123
    date, spots, regions = region_summary([
        dict(observed_date='2026-10-11', region=1, number_spots=10),
        dict(observed_date='2026-10-12', region=2, number_spots=3, area=50),
        dict(observed_date='2026-10-12', region=3, number_spots=2, area=90)])
    assert (date, spots) == ('2026-10-12', 5)
    assert regions[0]['region'] == 3
    assert 'ANTIGO' in observation_stamp('2026-10-01', datetime(2026,10,12,tzinfo=timezone.utc))


def test_panel_updates_and_source_failures(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(SolarObservingPanel, 'refresh_data', lambda self: calls.append(True))
    panel = SolarObservingPanel()
    panel.set_location(ObservatoryLocation('Casa'), True)
    assert calls
    assert 'Casa' in panel.local_info.text()
    panel._sdo_time(b'HMIIC: 20261012_150000')
    assert '12/10' in panel.visible.message
    panel._flux([dict(time_tag='2026-10-12T10:00:00', flux=130.2)])
    assert '130.2 sfu' in panel.flux.text()
    panel._regions([dict(observed_date='2026-10-12', region=1234, number_spots=5, mag_class='B', area=10)])
    assert '5 manchas' in panel.regions.text()
    panel._flares([dict(time_tag='2026-10-12T12:00:00Z', current_class='B1.0', max_class='M2.3', max_time='2026-10-12T11:00:00Z')])
    assert 'M2.3' in panel.flares.text()
    panel._image_failed(panel.halpha)
    assert 'indisponível' in panel.halpha.message
    panel.set_location(panel.location, False)
    assert not panel.timer.isActive()
    assert AppSettings(visible_panels=['solar']).visible_panels == ['solar']
    panel.close()


def test_continuum_timestamp_and_image_zoom():
    app = QApplication.instance() or QApplication([])
    panel = SolarObservingPanel()
    panel._sdo_time(b'magnetogram: 20261012_120000\ncontinuum: 20261013_195238\ncolorIc: 20261013_190000')
    assert '13/10 19:52' in panel.visible.stamp
    for target in (panel.visible, panel.halpha):
        target.image = QImage(1024, 1024, QImage.Format.Format_RGB32)
        target.image.fill(Qt.GlobalColor.white)
        QTest.mouseClick(target, Qt.MouseButton.LeftButton)
        app.processEvents()
        viewer = target.viewer
        assert viewer.isVisible()
        assert viewer.scene.itemsBoundingRect().width() == 1024
        scale = viewer.view.transform().m11()
        next(button for button in viewer.findChildren(QPushButton)
             if button.text() == '+').click()
        assert viewer.view.transform().m11() > scale
        viewer.close()
    panel.close()


@pytest.mark.parametrize('always_on_top', [False, True])
def test_click_in_scaled_panel_opens_native_viewer(always_on_top):
    app = QApplication.instance() or QApplication([])
    panel = SolarObservingPanel()
    fitted = FittedPanel(panel)
    fitted.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, always_on_top)
    fitted.resize(480, 400)
    fitted.show()
    app.processEvents()
    fitted.fit_content()
    for target in (panel.visible, panel.halpha):
        target.image = QImage(1024, 1024, QImage.Format.Format_RGB32)
        target.image.fill(Qt.GlobalColor.white)
        center = target.mapTo(panel, target.rect().center())
        position = fitted.mapFromScene(fitted.proxy.mapToScene(center))
        QTest.mouseClick(fitted.viewport(), Qt.MouseButton.LeftButton, pos=position)
        app.processEvents()
        assert target.viewer is not None
        assert target.viewer.isVisible()
        assert target.viewer.graphicsProxyWidget() is None
        assert target.viewer.parentWidget() is fitted
        assert target.viewer.windowHandle().transientParent() is fitted.windowHandle()
        assert bool(target.viewer.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) == always_on_top
        assert target.viewer.view.viewport().width() > target.width()
        target.viewer.close()
    fitted.close()


def test_gong_selects_newest_available_station(monkeypatch):
    app = QApplication.instance() or QApplication([])
    panel = SolarObservingPanel()
    requests = []
    monkeypatch.setattr(panel, '_get', lambda *args: requests.append(args))
    panel._gong_today()
    assert len(requests) == 5
    callbacks = list(requests)
    callbacks[0][2](b'<response><latestImage>/HA/hav/202610/20261012/20261012160034Ch.jpg</latestImage></response>')
    callbacks[1][2](b'<response><latestImage>/HA/hav/202610/20261012/20261012174922Th.jpg</latestImage></response>')
    for request in callbacks[2:]:
        request[3]()
    assert requests[-1][0] == 'gong_image'
    assert requests[-1][1].endswith('20261012174922Th.jpg')
    panel.close()

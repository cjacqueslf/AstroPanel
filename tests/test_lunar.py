from datetime import datetime, timezone
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from astropanel.domain.models import AppSettings, ObservatoryLocation
from astropanel.services.lunar import lunar_hour, lunar_sources, lunar_phase_name
from astropanel.ui.lunar import LunarObservingPanel
from astropanel.ui.fitted_panel import FittedPanel
from PySide6.QtWidgets import QApplication


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])

HOUR = datetime(2026, 10, 13, 21, tzinfo=timezone.utc)
ROOT = 'http://svs.gsfc.nasa.gov/vis/a000000/a005500/a005587/frames/'


def metadata():
    return dict(time='2026-10-13T21:00', phase=10.5, age=3.215,
                distance=399439, diameter=1794.3,
                image={'url': ROOT + '730x730_1x1_30p/moon.6862.jpg'},
                image_highres={'url': ROOT + '5760x3240_16x9_30p/fancy/comp.6862.tif'})


def test_lunar_metadata_and_phases():
    assert lunar_hour(HOUR.replace(minute=59)) == HOUR
    preview, atlas, labels = lunar_sources(metadata(), HOUR)
    assert preview.startswith('https://svs.gsfc.nasa.gov/')
    assert atlas.endswith('3840x2160_16x9_30p/plain/moon.6862.tif')
    assert labels.endswith('labels/label.6862.png')
    assert lunar_phase_name(3.2, 10.5) == 'Lua crescente'
    assert lunar_phase_name(25, 10.5) == 'Lua minguante'
    assert lunar_phase_name(0, 0) == 'Lua nova'
    assert lunar_phase_name(14.7, 100) == 'Lua cheia'
    assert lunar_phase_name(7, 50) == 'Quarto crescente'
    assert AppSettings(visible_panels=['solar', 'lunar']).visible_panels == ['solar', 'lunar']
    bad = metadata()
    bad['image']['url'] = 'https://example.com/image.jpg'
    with pytest.raises(ValueError):
        lunar_sources(bad, HOUR)
    bad = metadata()
    bad['image_highres']['url'] = bad['image_highres']['url'].replace('6862', '6861')
    with pytest.raises(ValueError):
        lunar_sources(bad, HOUR)
    with pytest.raises(ValueError):
        lunar_sources(metadata(), HOUR.replace(hour=22))


def image_bytes(width, height):
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.gray)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(buffer.data())


def test_lunar_pair_and_viewer_in_scaled_panel(app, monkeypatch):
    panel = LunarObservingPanel()
    requests = []
    monkeypatch.setattr(panel, '_get', lambda *args: requests.append(args))
    panel.location = ObservatoryLocation('Casa')
    panel._metadata(metadata(), HOUR)
    assert len(requests) == 3
    requests[0][2](image_bytes(730, 730))
    assert panel.moon.image.isNull()  # Do not expose mismatched image/atlas.
    requests[1][2](image_bytes(3840, 2160))
    assert panel.moon.image.isNull()
    requests[2][2](image_bytes(3840, 2160))
    assert panel.moon.image.width() == 730
    assert panel.moon.atlas.width() == panel.moon.atlas.height() == 2160
    assert panel.last_hour == HOUR
    assert '10.5%' in panel.phase.text()
    assert '13/10 21:00' in panel.moon.message
    fitted = FittedPanel(panel)
    fitted.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    fitted.resize(480, 400)
    fitted.show()
    app.processEvents()
    fitted.fit_content()
    center = panel.moon.mapTo(panel, panel.moon.rect().center())
    position = fitted.mapFromScene(fitted.proxy.mapToScene(center))
    QTest.mouseClick(fitted.viewport(), Qt.MouseButton.LeftButton, pos=position)
    app.processEvents()
    viewer = panel.moon.viewer
    assert viewer is not None and viewer.isVisible()
    assert viewer.parentWidget() is fitted
    assert viewer.graphicsProxyWidget() is None
    assert viewer.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert viewer.scene.itemsBoundingRect().width() == 2160
    panel._failed()
    assert 'anteriores' in panel.status.text()
    assert panel.moon.atlas.width() == 2160
    viewer.close()
    fitted.close()


def test_lunar_timer_and_failure(app, monkeypatch):
    panel = LunarObservingPanel()
    calls = []
    monkeypatch.setattr(panel, 'refresh_data', lambda: calls.append(True))
    panel.set_location(ObservatoryLocation('Casa'), True)
    assert calls and panel.timer.isActive()
    assert 'Casa' in panel.local_info.text()
    panel._failed()
    assert 'indisponível' in panel.moon.message
    panel.set_location(panel.location, False)
    assert not panel.timer.isActive()
    panel.close()

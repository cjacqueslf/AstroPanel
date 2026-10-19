import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPixmap, QColor, QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from astropanel.ui.widgets import SatelliteMapWidget
from astropanel.domain.models import ObservatoryLocation


@pytest.fixture
def satellite():
    app = QApplication.instance() or QApplication([])
    widget = SatelliteMapWidget()
    widget.resize(800,600)
    widget.map_pixmap = QPixmap(800,600)
    widget.map_pixmap.fill(QColor('#456789'))
    widget.location = ObservatoryLocation()
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def test_zoom_keeps_geographic_point_under_pointer(satellite):
    anchor = QPointF(440,320)
    before = satellite.image_rect()
    fraction = ((anchor.x()-before.x())/before.width(), (anchor.y()-before.y())/before.height())
    satellite.set_zoom(2, anchor)
    after = satellite.image_rect()
    assert (anchor.x()-after.x())/after.width() == pytest.approx(fraction[0])
    assert (anchor.y()-after.y())/after.height() == pytest.approx(fraction[1])
    assert satellite.pan_offset != QPointF()
    satellite.fit_button.click()
    assert satellite.zoom_factor == 1
    assert satellite.pan_offset == QPointF()


def test_wheel_buttons_drag_and_limits(satellite):
    event = QWheelEvent(QPointF(400,300), QPointF(400,300), QPoint(), QPoint(0,120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(satellite, event)
    assert satellite.zoom_factor > 1
    satellite.zoom_in_button.click()
    assert satellite.zoom_factor > 1.25
    satellite.set_zoom(2)
    QTest.mousePress(satellite, Qt.MouseButton.LeftButton, pos=QPoint(400,300))
    QTest.mouseMove(satellite, QPoint(480,340))
    QTest.mouseRelease(satellite, Qt.MouseButton.LeftButton, pos=QPoint(480,340))
    assert satellite.pan_offset.x() == pytest.approx(80)
    assert satellite.pan_offset.y() == pytest.approx(40)
    satellite.set_zoom(100)
    assert satellite.zoom_factor == 8
    assert not satellite.zoom_in_button.isEnabled()
    QTest.mouseDClick(satellite, Qt.MouseButton.LeftButton, pos=QPoint(400,300))
    assert satellite.zoom_factor == 1
    assert not satellite.zoom_out_button.isEnabled()


def test_pan_cannot_leave_empty_space_and_marker_moves_with_image(satellite):
    satellite.set_zoom(2)
    satellite.pan_offset = QPointF(10000,-10000)
    satellite._clamp_pan()
    rect = satellite.image_rect()
    assert rect.left() == pytest.approx(0)
    assert rect.bottom() == pytest.approx(600)
    assert not satellite.grab().isNull()


def test_new_location_resets_zoom_but_refresh_preserves_it(satellite, monkeypatch):
    from astropanel.services.map_providers import NasaGibsProvider
    from PySide6.QtCore import QObject, Signal
    class Reply(QObject):
        finished = Signal()
        def abort(self): pass
    monkeypatch.setattr(satellite.network, 'get', lambda request: Reply(satellite))
    satellite.provider_name = 'nasa_gibs_free'
    location = satellite.location
    satellite.set_zoom(2)
    satellite.set_location(location, 'nasa_gibs_free')
    assert satellite.zoom_factor == 2
    satellite.set_location(ObservatoryLocation(name='Outro local'), 'nasa_gibs_free')
    assert satellite.zoom_factor == 1

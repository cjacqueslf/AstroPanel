from PySide6.QtCore import QPointF
from astropanel.ui.widgets import WorldMapWidget


def test_map_center_is_zero_zero() -> None:
    latitude, longitude = WorldMapWidget.lat_lon_at(QPointF(180, 90), 360, 180)
    assert latitude == 0
    assert longitude == 0


def test_daynight_location_label_follows_name_and_visibility():
    from dataclasses import replace
    from PySide6.QtWidgets import QApplication
    from astropanel.domain.models import ObservatoryLocation
    app = QApplication.instance() or QApplication([])
    location = ObservatoryLocation(map_label='Meu observatório')
    widget = WorldMapWidget(location)
    widget.resize(650, 330)
    visible = widget.grab().toImage()
    widget.set_location(replace(location, map_label='Outro local'))
    renamed = widget.grab().toImage()
    assert visible != renamed
    widget.set_location(replace(location, show_map_label=False))
    hidden = widget.grab().toImage()
    assert visible != hidden
    widget.set_location(replace(location, map_label='Outro local', show_map_label=False))
    assert widget.grab().toImage() == hidden

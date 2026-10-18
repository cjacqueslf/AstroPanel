from datetime import datetime, timezone

import pytest
from astropanel.domain.models import ObservatoryLocation
from astropanel.services.sky import calculate_sky, catalog


def test_sky_catalog_and_day_night_positions(monkeypatch):
    monkeypatch.setattr('astropy.utils.iers.iers.download_file', lambda *a, **kw: pytest.fail('Unexpected network'))
    location = ObservatoryLocation()
    day = calculate_sky(location, datetime(2026, 10, 18, 15, tzinfo=timezone.utc))
    night = calculate_sky(location, datetime(2026, 10, 18, 3, tzinfo=timezone.utc))
    assert day.sun_altitude > 0
    assert night.sun_altitude < -18
    assert len(day.stars) > 4000
    assert len(day.bodies) == 9
    assert len(day.labels) == 89  # Serpens has two label positions.
    assert len(day.milky_way) == 361
    assert all(0 <= az < 360 and -90 <= alt <= 90 for _, az, alt in day.bodies)
    assert any(name == 'Sirius' for _, _, _, name in day.stars)


def test_naive_time_rejected():
    with pytest.raises(ValueError):
        calculate_sky(ObservatoryLocation(), datetime(2026, 1, 1))


def test_sky_canvas_renders_day_and_night():
    from PySide6.QtWidgets import QApplication
    from astropanel.ui.sky import SkyCanvas
    app = QApplication.instance() or QApplication([])
    canvas = SkyCanvas()
    canvas.resize(900, 700)
    for hour in (3, 15):
        canvas.snapshot = calculate_sky(ObservatoryLocation(), datetime(2026, 10, 18, hour, tzinfo=timezone.utc))
        assert not canvas.grab().isNull()

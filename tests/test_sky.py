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


def test_reference_lines_follow_equator_and_ecliptic_of_date():
    import numpy as np
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord, TETE, GeocentricTrueEcliptic
    from astropy.time import Time
    from astropy.utils import iers
    location = ObservatoryLocation()
    moment = datetime(2026,10,18,3,tzinfo=timezone.utc)
    sky = calculate_sky(location,moment)
    assert set(sky.reference_lines)=={'meridian','equator','ecliptic'}
    meridian = sky.reference_lines['meridian']
    assert meridian[0]==(0,0)
    assert meridian[-1]==(180,0)
    assert (0,90) in meridian
    observer=EarthLocation.from_geodetic(location.longitude*u.deg,location.latitude*u.deg,location.altitude_m*u.m)
    frame=AltAz(obstime=Time(moment),location=observer,pressure=0*u.hPa)
    with iers.conf.set_temp('auto_download',False), iers.conf.set_temp('auto_max_age',None):
        def coordinates(key):
            az,alt=zip(*sky.reference_lines[key])
            assert len(az)==361
            return SkyCoord(az=np.array(az)*u.deg,alt=np.array(alt)*u.deg,frame=frame)
        equator=coordinates('equator').transform_to(TETE(obstime=Time(moment)))
        assert np.max(np.abs(equator.dec.degree))<1e-5
        ecliptic=coordinates('ecliptic').transform_to(GeocentricTrueEcliptic(equinox=Time(moment),obstime=Time(moment)))
        assert np.max(np.abs(ecliptic.lat.degree))<1e-5
        sun=next(body for body in sky.bodies if body[0]=='Sol')
        sun_position=SkyCoord(az=sun[1]*u.deg,alt=sun[2]*u.deg,frame=frame)
        assert np.min(coordinates('ecliptic').separation(sun_position).degree)<.51


def test_reference_checkboxes_independently_show_and_hide_lines():
    from PySide6.QtWidgets import QApplication
    from astropanel.ui.sky import SkyNowDialog
    app=QApplication.instance() or QApplication([])
    dialog=SkyNowDialog(None)
    dialog.location=ObservatoryLocation()
    dialog.receive(calculate_sky(dialog.location,datetime(2026,10,18,3,tzinfo=timezone.utc)))
    for key in ('meridian','ecliptic','equator'):
        assert dialog.layer_checks[key].isChecked()
        visible=dialog.canvas.grab().toImage()
        dialog.layer_checks[key].click()
        assert getattr(dialog.canvas,key) is False
        assert dialog.canvas.grab().toImage()!=visible
        assert all(getattr(dialog.canvas,other) for other in ('meridian','ecliptic','equator') if other!=key)
        dialog.layer_checks[key].click()
        assert getattr(dialog.canvas,key) is True
    dialog.close()

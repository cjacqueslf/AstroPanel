from datetime import date, datetime, timedelta, timezone

import astropy.units as u
import pytest
from astropy.coordinates import AltAz, EarthLocation, get_body
from astropy.time import Time
from astropy.utils import iers

from astropanel.domain.models import ObservatoryLocation
from astropanel.services.planets import altitude_intervals, calculate_planet_night


def test_interpolated_visibility_intersects_twilight():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = (start, start + timedelta(hours=1), start + timedelta(hours=2))
    windows = altitude_intervals(times, (10, 30, 10), 20, (0, -12, -24))
    assert len(windows) == 1
    assert windows[0].start == start + timedelta(minutes=30)
    assert windows[0].end == start + timedelta(minutes=90)
    assert not altitude_intervals(times, (30, 40, 30), 20, (5, 4, 3))
    assert not altitude_intervals(times, (-10, -20, -10))


def test_real_planet_tracks_are_topocentric_and_ordered(monkeypatch):
    # A new planetary calculation must not try to fetch Earth-rotation tables.
    monkeypatch.setattr("astropy.utils.iers.iers.download_file", lambda *args, **kwargs: pytest.fail("Unexpected IERS download"))
    location = ObservatoryLocation()
    night = calculate_planet_night(location, date(2026, 10, 3))
    assert len(night.tracks) == 9
    assert [t.name for t in night.tracks] == ["Sol", "Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno", "Urano", "Netuno", "Lua"]
    assert not night.tracks[0].favorable
    assert len(night.moments) == 145
    assert (night.moments[-1] - night.moments[0]).total_seconds() == 86400
    observer = EarthLocation.from_geodetic(location.longitude * u.deg, location.latitude * u.deg, location.altitude_m * u.m)
    moment = Time(night.moments[72])
    with iers.conf.set_temp("auto_download", False), iers.conf.set_temp("auto_max_age", None):
        expected = get_body("jupiter", moment, observer, ephemeris="builtin").transform_to(
            AltAz(obstime=moment, location=observer, pressure=0 * u.hPa)).alt.degree
    assert night.tracks[4].altitudes[72] == pytest.approx(expected, abs=1e-5)
    for track in night.tracks:
        assert all(-90 <= h <= 90 for h in track.altitudes)
        for intervals in (track.above_horizon, track.favorable):
            for window in intervals:
                assert night.moments[0] <= window.start < window.end <= night.moments[-1]
        for window in track.favorable:
            assert any(h.start <= window.start and window.end <= h.end for h in track.above_horizon)


def test_planet_window_uses_actual_dst_duration():
    location = ObservatoryLocation("New York", 40.7, -74, 0, "America/New_York")
    night = calculate_planet_night(location, date(2026, 10, 31))
    assert (night.moments[-1] - night.moments[0]).total_seconds() == 25 * 3600

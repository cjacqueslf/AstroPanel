from datetime import date, datetime, timedelta, timezone

from astral import Observer
from astral.moon import elevation as moon_elevation
from astral.sun import elevation as sun_elevation

from astropanel.domain.models import ObservatoryLocation
from astropanel.services.astronomy import (
    MoonlessWindow, _below_horizon_intervals, calculate_moonless_windows, moonless_status,
)

UTC = timezone.utc
START = datetime(2026, 1, 1, tzinfo=UTC)


def test_intersection_can_have_multiple_windows():
    end = START + timedelta(hours=6)
    hours = lambda t: (t - START).total_seconds() / 3600
    windows = _below_horizon_intervals(
        START, end, lambda t: -1,
        lambda t: -(hours(t) - 1) * (hours(t) - 3),
    )
    assert len(windows) == 2
    assert windows[0].start == START
    assert abs((windows[0].end - START).total_seconds() - 3600) < 1
    assert abs((windows[1].start - START).total_seconds() - 10800) < 1
    assert windows[1].end == end


def test_no_darkness_and_full_interval():
    end = START + timedelta(hours=24)
    assert _below_horizon_intervals(START, end, lambda t: 1, lambda t: -1) == ()
    assert _below_horizon_intervals(START, end, lambda t: -1, lambda t: -1) == (MoonlessWindow(START, end),)


def test_real_windows_satisfy_both_conditions():
    location = ObservatoryLocation()
    observer = Observer(location.latitude, location.longitude, location.altitude_m)
    windows = calculate_moonless_windows(location, date(2026, 6, 15))
    assert windows
    for window in windows:
        assert window.duration > timedelta(0)
        middle = window.start + window.duration / 2
        assert sun_elevation(observer, middle, with_refraction=False) < -18
        assert moon_elevation(observer, middle.astimezone(UTC)) < 0
        assert window.start.tzinfo is not None


def test_polar_summer_has_no_window():
    location = ObservatoryLocation('Tromso', 69.6492, 18.9553, 0, 'Europe/Oslo')
    assert calculate_moonless_windows(location, date(2026, 6, 21)) == ()


def test_countdown_at_boundaries():
    window = MoonlessWindow(START + timedelta(hours=1), START + timedelta(hours=2))
    assert '01:00:00' in moonless_status((window,), START)
    assert '01:00:00' in moonless_status((window,), window.start)
    assert '00:00:01' in moonless_status((window,), window.end - timedelta(seconds=1))
    assert 'encerradas' in moonless_status((window,), window.end)
    assert 'Sem janela' in moonless_status((), START)


def test_next_moonset_skips_past_and_missing_events(monkeypatch):
    import astropanel.services.astronomy as astronomy
    location = ObservatoryLocation(timezone="UTC")
    future = START + timedelta(days=2, hours=3)
    events = {START.date(): START - timedelta(hours=1), future.date(): future}
    monkeypatch.setattr(astronomy, "_event", lambda call, observer, day, tz: events.get(day))
    assert astronomy.next_moonset(location, START) == future
    assert astronomy.moonset_countdown(future, START).endswith("51:00:00")
    assert astronomy.moonset_countdown(None, START)

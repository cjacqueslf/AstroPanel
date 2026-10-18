from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from astral import Observer
from astral.moon import elevation as moon_elevation, moonrise, moonset, phase
from astral.sun import dawn, noon, sunrise, sunset, dusk, elevation as sun_elevation
from astropy.time import Time
import astropy.units as u

from astropanel.domain.models import ObservatoryLocation


@dataclass(frozen=True)
class SunMoonInfo:
    sunrise: datetime | None
    sunset: datetime | None
    solar_noon: datetime | None
    astro_dawn: datetime | None
    astro_dusk: datetime | None
    civil_dawn: datetime | None
    civil_dusk: datetime | None
    nautical_dawn: datetime | None
    nautical_dusk: datetime | None
    moonrise: datetime | None
    moonset: datetime | None
    moon_phase_days: float
    illumination_percent: float
    astronomical_night: timedelta | None
    next_moon_phases: tuple[tuple[str, date], ...]


def _event(callable_, observer: Observer, day: date, tz: ZoneInfo, **kwargs) -> datetime | None:
    try:
        return callable_(observer, date=day, tzinfo=tz, **kwargs)
    except (ValueError, TypeError):
        return None


def calculate_sun_moon(location: ObservatoryLocation, day: date | None = None) -> SunMoonInfo:
    tz = ZoneInfo(location.timezone)
    day = day or datetime.now(tz).date()
    observer = Observer(latitude=location.latitude, longitude=location.longitude, elevation=location.altitude_m)
    astro_dawn = _event(dawn, observer, day, tz, depression=18)
    astro_dusk = _event(dusk, observer, day, tz, depression=18)
    civil_dawn = _event(dawn, observer, day, tz, depression=6)
    civil_dusk = _event(dusk, observer, day, tz, depression=6)
    nautical_dawn = _event(dawn, observer, day, tz, depression=12)
    nautical_dusk = _event(dusk, observer, day, tz, depression=12)
    # The useful observing interval crosses midnight: dusk of this date to dawn tomorrow.
    next_dawn = _event(dawn, observer, day + timedelta(days=1), tz, depression=18)
    night = next_dawn - astro_dusk if astro_dusk and next_dawn else None
    lunar_phase = phase(day)
    # Astral phase is 0..28, new at 0 and 28, full at 14.
    illumination = (1 - abs(lunar_phase - 14) / 14) * 100
    next_phases: list[tuple[str, date]] = []
    for name, target in (("Nova", 0), ("Quarto crescente", 7), ("Cheia", 14), ("Quarto minguante", 21)):
        days_until = (target - lunar_phase) % 28
        if days_until < 0.4:
            days_until = 0
        next_phases.append((name, day + timedelta(days=round(days_until))))
    return SunMoonInfo(
        sunrise=_event(sunrise, observer, day, tz),
        sunset=_event(sunset, observer, day, tz),
        solar_noon=_event(noon, observer, day, tz),
        astro_dawn=astro_dawn,
        astro_dusk=astro_dusk,
        civil_dawn=civil_dawn,
        civil_dusk=civil_dusk,
        nautical_dawn=nautical_dawn,
        nautical_dusk=nautical_dusk,
        moonrise=_event(moonrise, observer, day, tz),
        moonset=_event(moonset, observer, day, tz),
        moon_phase_days=lunar_phase,
        illumination_percent=max(0, min(100, illumination)),
        astronomical_night=night,
        next_moon_phases=tuple(sorted(next_phases, key=lambda item: item[1])),
    )


def moon_altitude_series(location: ObservatoryLocation, day: date) -> tuple[float, ...]:
    """Altitude lunar em uma janela contínua local de meio-dia a meio-dia."""
    tz = ZoneInfo(location.timezone)
    observer = Observer(latitude=location.latitude, longitude=location.longitude, elevation=location.altitude_m)
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=12)
    # astral.moon.elevation usa a data/hora como UTC internamente; converter o
    # instante local evita deslocar a curva pelo valor do fuso horário.
    return tuple(
        moon_elevation(observer, (start + timedelta(minutes=15 * sample)).astimezone(timezone.utc))
        for sample in range(97)
    )


def local_sidereal_time(location: ObservatoryLocation, moment: datetime | None = None) -> str:
    moment = moment or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("O instante deve ter fuso horário.")
    value = Time(moment.astimezone(timezone.utc), scale="utc").sidereal_time("apparent", longitude=location.longitude * u.deg)
    total_seconds = round(value.hour * 3600) % 86400
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


@dataclass(frozen=True)
class MoonlessWindow:
    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end.astimezone(timezone.utc) - self.start.astimezone(timezone.utc)


def _below_horizon_intervals(start: datetime, end: datetime, solar_height, lunar_height) -> tuple[MoonlessWindow, ...]:
    """Find crossings on a five-minute grid, refined to within one second."""
    boundaries = {start, end}
    for height in (solar_height, lunar_height):
        left = start
        left_value = height(left)
        while left < end:
            right = min(left + timedelta(minutes=5), end)
            right_value = height(right)
            if (left_value < 0) != (right_value < 0):
                low, high = left, right
                while (high - low).total_seconds() > 1:
                    middle = low + (high - low) / 2
                    if (height(middle) < 0) == (left_value < 0):
                        low = middle
                    else:
                        high = middle
                boundaries.add(low + (high - low) / 2)
            left, left_value = right, right_value
    points = sorted(boundaries)
    windows: list[MoonlessWindow] = []
    for left, right in zip(points, points[1:]):
        middle = left + (right - left) / 2
        if solar_height(middle) < 0 and lunar_height(middle) < 0:
            if windows and windows[-1].end == left:
                windows[-1] = MoonlessWindow(windows[-1].start, right)
            else:
                windows.append(MoonlessWindow(left, right))
    return tuple(windows)


def calculate_moonless_windows(location: ObservatoryLocation, day: date) -> tuple[MoonlessWindow, ...]:
    """Night of day: local noon to next noon, Sun < -18° and Moon < 0°.

    UTC arithmetic keeps elapsed durations correct across daylight saving changes.
    Horizon is the Astral lunar altitude, without terrain or weather modeling.
    """
    tz = ZoneInfo(location.timezone)
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=12)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=tz) + timedelta(hours=12)
    observer = Observer(location.latitude, location.longitude, location.altitude_m)
    windows = _below_horizon_intervals(
        start.astimezone(timezone.utc), end.astimezone(timezone.utc),
        lambda moment: sun_elevation(observer, moment, with_refraction=False) + 18,
        lambda moment: moon_elevation(observer, moment),
    )
    return tuple(MoonlessWindow(w.start.astimezone(tz), w.end.astimezone(tz)) for w in windows)


def moonless_status(windows: tuple[MoonlessWindow, ...], moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("O instante deve ter fuso horário.")
    now = moment.astimezone(timezone.utc)
    for window in windows:
        start, end = window.start.astimezone(timezone.utc), window.end.astimezone(timezone.utc)
        if now < end:
            remaining = (start if now < start else end) - now
            seconds = max(0, int(remaining.total_seconds()))
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            prefix = "Começa em" if now < start else "Em andamento · termina em"
            return f"{prefix} {hours:02}:{minutes:02}:{seconds:02}"
    return "Janelas desta noite encerradas." if windows else "Sem janela sem Lua nesta noite."


def next_moonset(location: ObservatoryLocation, moment: datetime) -> datetime | None:
    """Next lunar setting, including days without a setting at high latitudes."""
    if moment.tzinfo is None:
        raise ValueError("O instante deve ter fuso horário.")
    tz = ZoneInfo(location.timezone)
    observer = Observer(location.latitude, location.longitude, location.altitude_m)
    day = moment.astimezone(tz).date()
    for offset in range(32):
        event = _event(moonset, observer, day + timedelta(days=offset), tz)
        if event and event.astimezone(timezone.utc) > moment.astimezone(timezone.utc):
            return event
    return None


def moonset_countdown(event: datetime | None, moment: datetime) -> str:
    if event is None:
        return "Sem pôr da Lua nos próximos 32 dias."
    seconds = max(0, int((event.astimezone(timezone.utc) - moment.astimezone(timezone.utc)).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"Lua se põe em {hours:02}:{minutes:02}:{seconds:02}"

"""Offline topocentric planetary altitude timelines using Astropy's built-in ephemeris."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, get_body
from astropy.time import Time
from astropy.utils import iers

from astropanel.domain.models import ObservatoryLocation
from astropanel.services.astronomy import MoonlessWindow

PLANETS = {"mercury": "Mercúrio", "venus": "Vênus", "mars": "Marte", "jupiter": "Júpiter",
           "saturn": "Saturno", "uranus": "Urano", "neptune": "Netuno"}


@dataclass(frozen=True)
class PlanetTrack:
    name: str
    altitudes: tuple[float, ...]
    above_horizon: tuple[MoonlessWindow, ...]
    favorable: tuple[MoonlessWindow, ...]


@dataclass(frozen=True)
class PlanetNight:
    moments: tuple[datetime, ...]
    tracks: tuple[PlanetTrack, ...]


def altitude_intervals(moments, altitudes, minimum=0, solar=None):
    """Intersect linearly interpolated altitude and optional civil-darkness limits."""
    windows = []
    for i in range(len(moments) - 1):
        begin, end = 0.0, 1.0
        limits = [(altitudes[i] - minimum, altitudes[i + 1] - minimum)]
        if solar is not None:
            limits.append((-6 - solar[i], -6 - solar[i + 1]))
        for a, b in limits:
            if a <= 0 and b <= 0:
                end = begin
                break
            if (a > 0) != (b > 0):
                crossing = -a / (b - a)
                if a <= 0:
                    begin = max(begin, crossing)
                else:
                    end = min(end, crossing)
        if begin < end:
            span = moments[i + 1] - moments[i]
            start, finish = moments[i] + span * begin, moments[i] + span * end
            if windows and abs((windows[-1].end - start).total_seconds()) < .001:
                windows[-1] = MoonlessWindow(windows[-1].start, finish)
            else:
                windows.append(MoonlessWindow(start, finish))
    return tuple(windows)


def calculate_planet_night(location: ObservatoryLocation, day: date) -> PlanetNight:
    tz = ZoneInfo(location.timezone)
    start = (datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=12)).astimezone(timezone.utc)
    end = (datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=tz) + timedelta(hours=12)).astimezone(timezone.utc)
    moments = tuple(start + (end - start) * i / 144 for i in range(145))
    times = Time(moments)
    observer = EarthLocation.from_geodetic(location.longitude * u.deg, location.latitude * u.deg, location.altitude_m * u.m)
    frame = AltAz(obstime=times, location=observer, pressure=0 * u.hPa)
    # Avoid network requests for Earth-rotation tables; use bundled IERS data.
    with (iers.conf.set_temp("auto_download", False),
          iers.conf.set_temp("auto_max_age", None),
          iers.conf.set_temp("iers_leap_second_auto_url", ""),
          iers.conf.set_temp("ietf_leap_second_auto_url", "")):
        solar = tuple(get_body("sun", times, observer, ephemeris="builtin").transform_to(frame).alt.degree)
        solar = tuple(float(v) for v in solar)
        tracks = [PlanetTrack("Sol", solar, altitude_intervals(moments, solar), ())]
        for key, name in PLANETS.items():
            heights = tuple(float(v) for v in get_body(key, times, observer, ephemeris="builtin").transform_to(frame).alt.degree)
            tracks.append(PlanetTrack(name, heights, altitude_intervals(moments, heights),
                                      altitude_intervals(moments, heights, 20, solar)))
        lunar = tuple(float(v) for v in get_body("moon", times, observer, ephemeris="builtin").transform_to(frame).alt.degree)
        tracks.append(PlanetTrack("Lua", lunar, altitude_intervals(moments, lunar),
                                  altitude_intervals(moments, lunar, 20, solar)))
    return PlanetNight(moments, tuple(tracks))

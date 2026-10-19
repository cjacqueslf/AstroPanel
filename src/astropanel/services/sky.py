"""Offline sky positions for the observatory, with bundled bright-star data."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path

import numpy as np
import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, GeocentricTrueEcliptic, SkyCoord, TETE, get_body
from astropy.time import Time
from astropy.utils import iers
from astropanel.services.planets import PLANETS


@lru_cache(maxsize=1)
def catalog():
    root = Path(__file__).resolve().parents[1] / 'resources'
    def read(name):
        return json.loads((root / name).read_text(encoding='utf-8'))
    names = read('starnames.json')
    stars = [(f['geometry']['coordinates'], float(f['properties']['mag']),
              names.get(str(f['id']), {}).get('name', '')) for f in read('stars.6.json')['features']]
    lines = [line for f in read('constellations.lines.json')['features'] for line in f['geometry']['coordinates']]
    labels = [(f['geometry']['coordinates'], f['properties']['name']) for f in read('constellations.json')['features']]
    return stars, lines, labels


@dataclass
class SkySnapshot:
    moment: datetime
    stars: list
    lines: list
    labels: list
    milky_way: list
    bodies: list
    sun_altitude: float
    moon_illumination: float
    moon_light_angle: float
    reference_lines: dict = field(default_factory=dict)


def calculate_sky(location, moment=None):
    moment = moment or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError('O instante deve ter fuso horário.')
    observer = EarthLocation.from_geodetic(location.longitude*u.deg, location.latitude*u.deg, location.altitude_m*u.m)
    time = Time(moment)
    frame = AltAz(obstime=time, location=observer, pressure=0*u.hPa)
    stars, lines, labels = catalog()
    def transform(points):
        values = np.asarray(points)
        coords = SkyCoord(ra=values[:, 0]*u.deg, dec=values[:, 1]*u.deg).transform_to(frame)
        return list(zip(coords.az.degree.tolist(), coords.alt.degree.tolist()))
    with (iers.conf.set_temp('auto_download', False), iers.conf.set_temp('auto_max_age', None),
          iers.conf.set_temp('iers_leap_second_auto_url', ''),
          iers.conf.set_temp('ietf_leap_second_auto_url', '')):
        positions = transform([s[0] for s in stars])
        flat_lines = transform([p for line in lines for p in line])
        result_lines = []
        offset = 0
        for line in lines:
            result_lines.append(flat_lines[offset:offset+len(line)])
            offset += len(line)
        label_positions = transform([s[0] for s in labels])
        galactic = SkyCoord(l=np.arange(361)*u.deg, b=np.zeros(361)*u.deg, frame='galactic').icrs
        milky_way = transform(list(zip(galactic.ra.degree, galactic.dec.degree)))
        angles = np.arange(361)*u.deg
        equator = SkyCoord(ra=angles, dec=np.zeros(361)*u.deg,
                           frame=TETE(obstime=time)).transform_to(frame)
        ecliptic = SkyCoord(lon=angles, lat=np.zeros(361)*u.deg,
                            frame=GeocentricTrueEcliptic(equinox=time, obstime=time)).transform_to(frame)
        reference_lines = {
            'meridian': [(0., float(alt)) for alt in range(91)]
                        + [(180., float(alt)) for alt in range(89, -1, -1)],
            'equator': list(zip(equator.az.degree.tolist(), equator.alt.degree.tolist())),
            'ecliptic': list(zip(ecliptic.az.degree.tolist(), ecliptic.alt.degree.tolist())),
        }
        bodies = []
        coordinates = {}
        for key, name in {'sun': 'Sol', 'moon': 'Lua', **PLANETS}.items():
            coordinates[key] = get_body(key, time, observer, ephemeris='builtin')
            pos = coordinates[key].transform_to(frame)
            bodies.append((name, float(pos.az.degree), float(pos.alt.degree)))
        sun, moon = coordinates['sun'], coordinates['moon']
        elongation = sun.separation(moon).rad
        phase = np.arctan2(sun.distance.to_value(u.au)*np.sin(elongation),
                           moon.distance.to_value(u.au)-sun.distance.to_value(u.au)*np.cos(elongation))
        illumination = float((1+np.cos(phase))/2)
        # Project the direction toward the Sun onto the all-sky map at the Moon.
        def vector(az, alt):
            az, alt = np.radians([az, alt])
            return np.array([np.cos(alt)*np.sin(az), np.cos(alt)*np.cos(az), np.sin(alt)])
        sun_vector = vector(*bodies[0][1:])
        moon_vector = vector(*bodies[1][1:])
        tangent = sun_vector-np.dot(sun_vector, moon_vector)*moon_vector
        nearby = moon_vector+0.001*tangent
        nearby /= np.linalg.norm(nearby)
        def project(az, alt):
            return np.array([-(90-alt)*np.sin(np.radians(az)), -(90-alt)*np.cos(np.radians(az))])
        near_az = np.degrees(np.arctan2(nearby[0], nearby[1]))
        near_alt = np.degrees(np.arcsin(np.clip(nearby[2], -1, 1)))
        delta = project(near_az, near_alt)-project(*bodies[1][1:])
        light_angle = float(np.degrees(np.arctan2(delta[1], delta[0])))
    return SkySnapshot(moment, [(az, alt, mag, name) for (az, alt), (_, mag, name) in zip(positions, stars)],
                       result_lines, [(az, alt, name) for (az, alt), (_, name) in zip(label_positions, labels)],
                       milky_way, bodies, bodies[0][2], illumination, light_angle, reference_lines)

"""Deep-sky name resolution and local equatorial-to-horizontal tracks."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from urllib.parse import quote
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import astropy.units as u
from astropy.coordinates import Angle, AltAz, EarthLocation, SkyCoord
from astropy.time import Time
from astropy.utils import iers
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


@dataclass(frozen=True)
class DeepSkyObject:
    name: str
    ra_deg: float
    dec_deg: float
    source: str = 'Personalizado'

    def __post_init__(self):
        if not (math.isfinite(self.ra_deg) and math.isfinite(self.dec_deg)
                and 0 <= self.ra_deg < 360 and -90 <= self.dec_deg <= 90):
            raise ValueError('AR deve estar entre 0h e menos de 24h; declinação entre −90° e +90°.')

    def coordinate_text(self):
        coordinate = SkyCoord(self.ra_deg*u.deg, self.dec_deg*u.deg)
        return (coordinate.ra.to_string(unit=u.hourangle, sep=':', precision=2, pad=True),
                coordinate.dec.to_string(unit=u.deg, sep=':', precision=1, alwayssign=True, pad=True))


def catalog_name(text):
    match = re.fullmatch(r'\s*(MESSIER|M|NGC|IC|PGC)\s*0*(\d+)([A-Z]?)\s*', text.upper())
    if not match or int(match[2]) < 1:
        raise ValueError('Digite um identificador como M 31, NGC 253, IC 434 ou PGC 2557.')
    prefix = 'M' if match[1] == 'MESSIER' else match[1]
    return f'{prefix} {int(match[2])}{match[3]}'


def parse_coordinates(name, ra, dec):
    try:
        right_ascension = Angle(ra.strip(), unit=u.hourangle).hour
        declination = Angle(dec.strip(), unit=u.deg).degree
        return DeepSkyObject(name.strip() or 'Objeto personalizado', float(right_ascension)*15, float(declination))
    except (ValueError, TypeError, u.UnitsError) as error:
        raise ValueError('Coordenadas inválidas. Use AR em h:m:s (ou horas decimais) e DEC em graus, com sinal.') from error


def parse_sesame(payload, name):
    try:
        root = ElementTree.fromstring(payload)
        for resolver in root.findall('.//Resolver'):
            ra, dec = resolver.findtext('jradeg'), resolver.findtext('jdedeg')
            if ra is not None and dec is not None:
                return DeepSkyObject(name, float(ra), float(dec), 'CDS/Sesame')
    except (ElementTree.ParseError, ValueError) as error:
        raise ValueError('Resposta de coordenadas inválida do CDS/Sesame.') from error
    raise ValueError(f'{name}: objeto não encontrado. Confira o identificador ou informe as coordenadas manualmente.')


def object_altitude_series(target, location, day):
    start = datetime.combine(day, datetime.min.time(), tzinfo=ZoneInfo(location.timezone))+timedelta(hours=12)
    # Use exactly the same local sampling as the existing lunar chart.
    times = Time([(start+timedelta(minutes=15*i)).astimezone(timezone.utc) for i in range(97)])
    return object_altitudes_at(target, location, times)


def object_altitudes_at(target, location, moments):
    times = moments if isinstance(moments, Time) else Time(list(moments))
    observer = EarthLocation.from_geodetic(location.longitude*u.deg, location.latitude*u.deg, location.altitude_m*u.m)
    frame = AltAz(obstime=times, location=observer, pressure=0*u.hPa)
    with (iers.conf.set_temp('auto_download', False), iers.conf.set_temp('auto_max_age', None),
          iers.conf.set_temp('iers_leap_second_auto_url', ''), iers.conf.set_temp('ietf_leap_second_auto_url', '')):
        heights = SkyCoord(target.ra_deg*u.deg, target.dec_deg*u.deg, frame='icrs').transform_to(frame).alt.degree
    return tuple(float(value) for value in heights)


class DeepSkyResolver(QObject):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.reply = None
        self.generation = 0
        self.cache = {}

    def stop(self):
        self.generation += 1
        if self.reply is not None:
            self.reply.abort()
            self.reply = None

    def resolve(self, text):
        self.stop()
        try:
            name = catalog_name(text)
        except ValueError as error:
            self.failed.emit(str(error))
            return
        if name in self.cache:
            self.ready.emit(self.cache[name])
            return
        request = QNetworkRequest(QUrl('https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?'+quote(name)))
        request.setTransferTimeout(15000)
        reply = self.network.get(request)
        self.reply = reply
        generation = self.generation
        def finished():
            try:
                if generation != self.generation:
                    return
                self.reply = None
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise ValueError('Falha na busca do catálogo: '+reply.errorString()+'. Você pode informar as coordenadas manualmente.')
                target = parse_sesame(bytes(reply.readAll()), name)
                self.cache[name] = target
                self.ready.emit(target)
            except ValueError as error:
                self.failed.emit(str(error))
            finally:
                reply.deleteLater()
        reply.finished.connect(finished)

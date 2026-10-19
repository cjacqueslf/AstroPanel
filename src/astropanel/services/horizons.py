"""Topocentric moving-object ephemerides from NASA/JPL Horizons."""
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import re
import unicodedata
from urllib.parse import urlencode
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from astropanel.services.observation import night_bounds

ENDPOINT = 'https://ssd.jpl.nasa.gov/api/horizons.api'


def horizons_command(designation):
    text = ' '.join(designation.strip().split())
    if not text or len(text)>100 or not re.fullmatch(r'[\w /().+\-]+',text):
        raise ValueError('Informe uma designação, por exemplo 433, 2024 YR4, C/2023 A3 ou Marte.')
    plain = ''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c))
    major = {'sol':'10','sun':'10','mercurio':'199','mercury':'199','venus':'299',
             'terra':'399','earth':'399','lua':'301','moon':'301','marte':'499','mars':'499',
             'jupiter':'599','saturno':'699','saturn':'699','urano':'799','uranus':'799',
             'netuno':'899','neptune':'899','plutao':'999','pluto':'999'}
    if plain in major:
        return major[plain]
    if re.fullmatch(r'jpl\s+-?\d+',plain):
        return plain.split()[-1]
    if text.isdigit():
        return f'{int(text)};'
    if re.match(r'(?i)^(?:[CPDXAI]/|\d+[PDI](?:\b|/))',text):
        return f'DES={text};CAP'
    if re.fullmatch(r'\d{4}\s+[A-Za-z]{1,2}\d*',text):
        return f'DES={text.upper()};'
    return text


def horizons_url(designation, location, day):
    start,end = night_bounds(location,day)
    params = {'format':'json','COMMAND':horizons_command(designation), 'OBJ_DATA':'YES',
              'MAKE_EPHEM':'YES','EPHEM_TYPE':'OBSERVER','CENTER':'coord@399','COORD_TYPE':'GEODETIC',
              'SITE_COORD':f'{location.longitude},{location.latitude},{location.altitude_m/1000}',
              'START_TIME':start.strftime('%Y-%m-%d %H:%M:%S'),'STOP_TIME':end.strftime('%Y-%m-%d %H:%M:%S'),
              'STEP_SIZE':'1 m','QUANTITIES':'1,4','CSV_FORMAT':'YES','ANG_FORMAT':'DEG',
              'CAL_FORMAT':'JD','APPARENT':'AIRLESS','TIME_TYPE':'UT','REF_SYSTEM':'ICRF'}
    return ENDPOINT+'?'+urlencode({key:(value if key=='format' else f"'{value}'") for key,value in params.items()})


@dataclass(frozen=True)
class SolarEphemeris:
    designation: str
    name: str
    location: object
    day: object
    moments: tuple
    ra_degrees: tuple
    dec_degrees: tuple
    altitudes: tuple
    source: str = 'JPL Horizons'

    def coordinates_at(self, moment=None):
        moment = moment or datetime.now(timezone.utc)
        index = min(range(len(self.moments)),key=lambda i:abs((self.moments[i]-moment).total_seconds()))
        return self.ra_degrees[index], self.dec_degrees[index], self.moments[index]

    def coordinate_text(self, moment=None):
        ra,dec,_ = self.coordinates_at(moment)
        coord = SkyCoord(ra*u.deg,dec*u.deg,frame='icrs')
        return coord.ra.to_string(unit=u.hourangle,sep=':',precision=2,pad=True), coord.dec.to_string(
            unit=u.deg,sep=':',precision=1,pad=True,alwayssign=True)


def parse_horizons(payload, designation, location, day):
    if not isinstance(payload,dict):
        raise ValueError('Resposta inválida do JPL Horizons.')
    result = payload.get('result','')
    if not isinstance(result,str):
        raise ValueError('Resposta inválida do JPL Horizons.')
    error = str(payload.get('error',''))
    if '$$SOE' not in result or '$$EOE' not in result:
        message = (error+' '+result).lower()
        if any(text in message for text in ('no matches found','no matching','cannot find','no target matches','no such')):
            raise ValueError('Não existe objeto com essa designação no JPL Horizons. Confira o que foi digitado.')
        if any(text in message for text in ('multiple','matching small-bodies','matching major-bodies','matches found')):
            raise ValueError('A designação é ambígua no JPL. Informe o número ou uma designação mais específica.')
        raise ValueError('O JPL não retornou efemérides para essa designação e data. '+error[:250])
    match = re.search(r'^Target body name:\s*(.*?)\s*(?:\{|$)',result,re.M)
    name = match[1].strip() if match else designation
    rows = list(csv.reader(result.split('$$SOE',1)[1].split('$$EOE',1)[0].strip().splitlines()))
    try:
        numbers = [(float(row[0]),float(row[3]),float(row[4]),float(row[6])) for row in rows if row]
        if len(numbers)<2 or not all(all(math.isfinite(v) for v in row) for row in numbers):
            raise ValueError()
        moments = tuple(datetime.fromtimestamp(round(Time(row[0],format='jd',scale='utc').to_datetime(timezone.utc).timestamp()),timezone.utc) for row in numbers)
        if any(not 0<(b-a).total_seconds()<=61 for a,b in zip(moments,moments[1:])):
            raise ValueError()
        if any(not (0<=r[1]<360 and -90<=r[2]<=90 and -90<=r[3]<=90) for r in numbers):
            raise ValueError()
        start,end = night_bounds(location,day)
        if abs((moments[0]-start).total_seconds())>1 or abs((moments[-1]-end).total_seconds())>1:
            raise ValueError()
    except (ValueError, IndexError, TypeError) as exc:
        raise ValueError('Efemérides incompletas ou inválidas recebidas do JPL Horizons.') from exc
    return SolarEphemeris(designation,name,location,day,moments,tuple(r[1] for r in numbers),
                          tuple(r[2] for r in numbers),tuple(r[3] for r in numbers))


class HorizonsClient(QObject):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self,parent=None):
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

    def resolve(self,designation,location,day):
        self.stop()
        try:
            url = horizons_url(designation,location,day)
        except ValueError as exc:
            self.failed.emit(str(exc)); return
        key = (horizons_command(designation),location,day)
        if key in self.cache:
            self.ready.emit(self.cache[key]); return
        request = QNetworkRequest(QUrl(url)); request.setTransferTimeout(30000)
        reply = self.network.get(request); self.reply = reply
        generation = self.generation
        def finished():
            try:
                if generation!=self.generation:
                    return
                self.reply = None
                if reply.error()!=QNetworkReply.NetworkError.NoError:
                    raise ValueError('Não foi possível consultar o JPL: '+reply.errorString())
                target = parse_horizons(json.loads(bytes(reply.readAll())),designation,location,day)
                if len(self.cache)>=16:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = target
                self.ready.emit(target)
            except (ValueError,TypeError) as exc:
                self.failed.emit(str(exc))
            finally:
                reply.deleteLater()
        reply.finished.connect(finished)

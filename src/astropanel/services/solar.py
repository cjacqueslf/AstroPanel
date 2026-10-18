"""Source selection and interpretation for the solar observing panel."""
import re
from datetime import datetime, timezone

SDO_IMAGE = 'https://jsoc1.stanford.edu/data/hmi/images/latest/HMI_latest_Int_4096x4096.gif'
SDO_TIME = 'https://jsoc1.stanford.edu/data/hmi/images/latest/image_times_UTC'
GONG_ROOT = 'https://gong2.nso.edu/HA/hag/'
NOAA_ROOT = 'https://services.swpc.noaa.gov/json/'


def latest_gong_link(html, kind):
    patterns = {'month': r'(\d{6})/', 'day': r'(\d{8})/',
                'image': r'(\d{14}[BCLMTU]h\.jpg)'}
    links = re.findall(r'href=[\"\']([^\"\']+)', html)
    candidates = [link for link in links if re.fullmatch(patterns[kind], link)]
    if not candidates:
        raise ValueError('Nenhuma imagem GONG disponível')
    return max(candidates)


def gong_time(filename):
    return datetime.strptime(filename[:14], '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)


def gong_metadata_path(data):
    from xml.etree import ElementTree
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise ValueError("Metadados GONG inválidos") from error
    paths = [node.text for node in root.iter('latestImage') if node.text]
    valid = [path for path in paths if re.fullmatch(r'/HA/hav/\d{6}/\d{8}/\d{14}[BCLMTU]h\.jpg', path)]
    if not valid:
        raise ValueError('Metadados GONG sem imagem científica')
    return max(valid, key=lambda path: path.rsplit('/', 1)[-1])


def latest_record(rows, field='time_tag'):
    valid = [row for row in rows if isinstance(row, dict) and row.get(field)]
    if not valid:
        raise ValueError('Dados solares vazios')
    return max(valid, key=lambda row: row[field])


def region_summary(rows):
    date = latest_record(rows, 'observed_date')['observed_date']
    unique = {row['region']: row for row in rows if row.get('observed_date') == date
              and row.get('region') is not None}
    regions = sorted(unique.values(), key=lambda row: row.get('area') or 0, reverse=True)
    spots = sum(row.get('number_spots') or 0 for row in regions)
    return date, spots, regions


def observation_stamp(value, now=None):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds() / 3600
    return stamp.strftime('%d/%m %H:%M UTC') + (' · DADO ANTIGO' if age > 24 else '')

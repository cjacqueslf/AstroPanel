"""Hourly phase images and matching labelled atlas from NASA SVS."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

LUNAR_API = 'https://svs.gsfc.nasa.gov/api/dialamoon/'


def lunar_hour(moment=None):
    return (moment or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def lunar_sources(data, requested_hour):
    """Reject mismatched dates and external URLs before following metadata."""
    stamp = datetime.fromisoformat(data['time']).replace(tzinfo=timezone.utc)
    if stamp != requested_hour:
        raise ValueError('Imagem lunar fora do horário solicitado')
    paths = []
    for key in ('image', 'image_highres'):
        url = urlsplit(data[key]['url'])
        if url.hostname != 'svs.gsfc.nasa.gov' or url.scheme not in ('http', 'https'):
            raise ValueError('Fonte lunar inválida')
        paths.append(url.path)
    preview = re.fullmatch(r'(/vis/a\d{6}/a\d{6}/a\d{6}/frames/)730x730_1x1_30p/moon\.(\d{4})\.jpg', paths[0])
    atlas = re.fullmatch(r'(/vis/a\d{6}/a\d{6}/a\d{6}/frames/)5760x3240_16x9_30p/fancy/comp\.(\d{4})\.tif', paths[1])
    if not preview or not atlas or preview.groups() != atlas.groups():
        raise ValueError('Mapa lunar não corresponde à imagem')
    root, frame = preview.groups()
    base = 'https://svs.gsfc.nasa.gov' + root + '3840x2160_16x9_30p/'
    return ('https://svs.gsfc.nasa.gov' + paths[0],
            base + f'plain/moon.{frame}.tif',
            base + f'labels/label.{frame}.png')


def lunar_phase_name(age, illumination):
    if illumination < 1:
        return 'Lua nova'
    if illumination > 99:
        return 'Lua cheia'
    if 48 <= illumination <= 52:
        return 'Quarto crescente' if age < 14.765 else 'Quarto minguante'
    if age < 14.765:
        return 'Lua crescente' if illumination < 50 else 'Gibosa crescente'
    return 'Lua minguante' if illumination < 50 else 'Gibosa minguante'

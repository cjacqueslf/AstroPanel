"""Public InstaRain observations, independent of the website's service worker."""
import gzip
import json
import math
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

BASE_URL = 'https://www.instarain.com.br'


def normalize_stations(rows):
    if not isinstance(rows, list):
        raise ValueError('Resposta de estações inválida')
    result = []
    for row in rows:
        if not isinstance(row, dict) or row.get('Publico') is False:
            continue
        try:
            if row.get('Latitude') is None or row.get('Longitude') is None:
                continue
            lat, lon = float(row['Latitude']), float(row['Longitude'])
            if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat)>90 or abs(lon)>180:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        result.append(dict(id=row.get('Id'), name=row.get('Nome'), latitude=lat, longitude=lon,
                           condition=row.get('Clima'), weather=row.get('Tempo'), temperature=row.get('Temperatura'),
                           rain24h=row.get('Ultimas24h'), time=row.get('Data'), radius=row.get('RaioAcaoEstacao'),
                           online=row.get('Online')))
    return result


class InstaRainClient(QObject):
    ready = Signal(list)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.reply = None
        self._generation = 0

    def stop(self):
        self._generation += 1
        if self.reply:
            self.reply.abort()
            self.reply = None

    def refresh(self):
        if self.reply:
            return
        self._request('/oauth/authorize?app=web', self._authorized)

    def _request(self, path, callback, token=None):
        request = QNetworkRequest(QUrl(BASE_URL+path))
        request.setTransferTimeout(15000)
        if token:
            request.setRawHeader(b'Authorization', token.encode('utf-8'))
        generation = self._generation
        reply = self.network.get(request)
        self.reply = reply
        def finished():
            if generation != self._generation:
                reply.deleteLater()
                return
            self.reply = None
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise ValueError(reply.errorString())
                data = bytes(reply.readAll())
                if data.startswith(b'\x1f\x8b'):
                    data = gzip.decompress(data)
                callback(json.loads(data))
            except (ValueError, TypeError, KeyError, OSError) as exc:
                self.failed.emit(str(exc))
            finally:
                reply.deleteLater()
        reply.finished.connect(finished)

    def _authorized(self, auth):
        # Anonymous access token issued by the same open authorization flow as the site.
        self._request('/InstaRainApi/v1/meteorologicas?Online=True',
                      lambda rows: self.ready.emit(normalize_stations(rows)), auth['access_token'])

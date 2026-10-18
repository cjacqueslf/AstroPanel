"""Check the AstroPanel release channel without downloading or installing."""
from dataclasses import dataclass
import json
import re

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from astropanel import __version__

REPOSITORY = 'cjacqueslf/AstroPanel'
PRIVATE_CHANNEL = True
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'
LATEST_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'


def version_parts(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    if not match:
        raise ValueError('A versão publicada não usa o formato esperado (ex.: v0.1.0).')
    return tuple(map(int, match.groups()))


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    newer: bool


def parse_release(payload, current=__version__):
    if not isinstance(payload, dict) or payload.get('draft') or payload.get('prerelease'):
        raise ValueError('A resposta não contém uma versão estável publicada.')
    tag = payload.get('tag_name', '')
    parts = version_parts(tag)
    url = payload.get('html_url', '')
    if not url.startswith(RELEASES_URL+'/tag/'):
        raise ValueError('Endereço de versão inválido.')
    return ReleaseInfo(tag.removeprefix('v'), url, parts > version_parts(current))


class UpdateChecker(QObject):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.reply = None

    def check(self):
        if self.reply is not None:
            return
        request = QNetworkRequest(QUrl(LATEST_URL))
        request.setTransferTimeout(15000)
        request.setRawHeader(b'Accept', b'application/vnd.github+json')
        request.setRawHeader(b'User-Agent', f'AstroPanel/{__version__}'.encode('ascii'))
        self.reply = self.network.get(request)
        self.reply.finished.connect(self._finished)

    def _finished(self):
        reply, self.reply = self.reply, None
        try:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if status == 404:
                raise ValueError('O canal não está acessível sem autenticação ou ainda não tem uma versão publicada. Abra a página das versões com sua conta GitHub autorizada.')
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError('Não foi possível consultar o GitHub: '+reply.errorString())
            self.ready.emit(parse_release(json.loads(bytes(reply.readAll()))))
        except (ValueError, TypeError) as exc:
            self.failed.emit(str(exc))
        finally:
            reply.deleteLater()

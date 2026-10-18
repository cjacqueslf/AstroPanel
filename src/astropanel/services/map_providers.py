from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
from urllib.parse import urlencode, quote
import math

MAP_PROVIDERS = {
    "goes19_geocolor": "GOES-19 / NOAA · satélite gratuito",
    "goes19_infrared": "GOES-19 / NOAA · infravermelho · dia e noite",
    "nasa_gibs_free": "NASA GIBS · composição diária gratuita",
    "windy_clouds": "Windy · nuvens · mapa gratuito",
    "windy_lclouds": "Windy · nuvens baixas",
    "windy_mclouds": "Windy · nuvens médias",
    "windy_hclouds": "Windy · nuvens altas",
    "instarain": "InstaRain · mapa online",
    "windy_instarain": "Windy nuvens + InstaRain · camadas combinadas",
    "light_pollution": "Light Pollution Map · poluição luminosa",
    "ventusky": "Ventusky · nuvens e visibilidade",
    "none": "Desativado",
}


def weather_web_url(provider: str, latitude: float, longitude: float, name: str = "Observador") -> str:
    if provider == "windy_instarain":
        provider = "windy_clouds"
    if provider == "instarain":
        return "https://www.instarain.com.br/"
    if provider == "light_pollution":
        return "https://www.lightpollutionmap.info/#" + urlencode({
            "zoom": 7, "lat": latitude, "lon": longitude})
    if provider == "ventusky":
        return "https://www.ventusky.com/?" + urlencode({
            "p": f"{latitude};{longitude};7", "l": "clouds-total",
            "pin": f"{latitude};{longitude};dot;{name.replace(';', ',')}"}, quote_via=quote)
    if provider in ("windy_clouds", "windy_lclouds", "windy_mclouds", "windy_hclouds"):
        params = {"lat": latitude, "lon": longitude, "zoom": 7,
                  "level": "surface", "overlay": provider.removeprefix("windy_"),
                  "type": "map", "location": "coordinates", "marker": "true",
                  "detailLat": latitude, "detailLon": longitude,
                  "metricTemp": "°C", "metricWind": "km/h", "metricRain": "mm"}
        return "https://embed.windy.com/embed.html?" + urlencode(params)
    return ""

from PySide6.QtGui import QImage


class MapProvider(ABC):
    """Extensão para provedores remotos de imagem de satélite."""

    @abstractmethod
    def get_map(self, latitude: float, longitude: float, zoom: int, width: int, height: int) -> QImage:
        raise NotImplementedError

    @abstractmethod
    def build_url(self, latitude: float, longitude: float, zoom: int, width: int, height: int) -> str:
        raise NotImplementedError


class NoMapProvider(MapProvider):
    def get_map(self, latitude: float, longitude: float, zoom: int, width: int, height: int) -> QImage:
        return QImage()

    def build_url(self, latitude: float, longitude: float, zoom: int, width: int, height: int) -> str:
        return ""


class NasaGibsProvider(MapProvider):
    """Imagem global MODIS da NASA GIBS, livre e sem chave de API.

    É uma imagem de composição diária: útil para contexto regional, mas não deve
    ser apresentada como foto de alta resolução de um endereço específico.
    """

    endpoint = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"

    def get_map(self, latitude: float, longitude: float, zoom: int, width: int, height: int) -> QImage:
        return QImage()

    def build_url(self, latitude: float, longitude: float, zoom: int, width: int, height: int) -> str:
        # About 10° across at zoom 7, bounded to the WMS EPSG:4326 world extent.
        min_lat, min_lon, max_lat, max_lon = self.bounds(latitude, longitude, zoom)
        params = {
            "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0",
            "LAYERS": "MODIS_Terra_CorrectedReflectance_TrueColor", "STYLES": "",
            "FORMAT": "image/jpeg", "TRANSPARENT": "FALSE", "CRS": "EPSG:4326",
            # GIBS can lag real time; yesterday is normally an available daily layer.
            "TIME": (date.today() - timedelta(days=1)).isoformat(),
            "WIDTH": max(64, min(2048, width)), "HEIGHT": max(64, min(2048, height)),
            # WMS 1.3 EPSG:4326 uses latitude, longitude axis order.
            "BBOX": f"{min_lat},{min_lon},{max_lat},{max_lon}",
        }
        return f"{self.endpoint}?{urlencode(params)}"

    @staticmethod
    def bounds(latitude: float, longitude: float, zoom: int) -> tuple[float, float, float, float]:
        span = max(1.0, min(80.0, 180.0 / (2 ** (zoom - 3))))
        min_lon, max_lon = max(-180.0, longitude - span), min(180.0, longitude + span)
        min_lat, max_lat = max(-90.0, latitude - span / 2), min(90.0, latitude + span / 2)
        return min_lat, min_lon, max_lat, max_lon

    @classmethod
    def project_location(cls, latitude: float, longitude: float, zoom: int = 7) -> tuple[float, float]:
        min_lat, min_lon, max_lat, max_lon = cls.bounds(latitude, longitude, zoom)
        return ((longitude - min_lon) / (max_lon - min_lon),
                (max_lat - latitude) / (max_lat - min_lat))


class Goes19GeoColorProvider(NasaGibsProvider):
    """GOES-East georreferenciado pelo NASA GIBS, centrado no observador."""

    layer = "GOES-East_ABI_GeoColor"
    viewer_url = NasaGibsProvider.endpoint + "?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0"

    def build_url(self, latitude: float, longitude: float, zoom: int, width: int, height: int) -> str:
        return self.viewer_url

    @classmethod
    def latest_time(cls, capabilities: str) -> str | None:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(capabilities)
        except ET.ParseError:
            return None
        ns = {"wms": "http://www.opengis.net/wms"}
        for layer in root.findall(".//wms:Layer", ns):
            if layer.findtext("wms:Name", namespaces=ns) == cls.layer:
                for dimension in layer.findall("wms:Dimension", ns):
                    if dimension.get("name") == "time":
                        return dimension.get("default")
        return None

    def image_url(self, timestamp: str, latitude: float, longitude: float, zoom: int,
                  width: int, height: int) -> str:
        from urllib.parse import parse_qs, urlparse
        base = super().build_url(latitude, longitude, zoom, width, height)
        params = {key: value[0] for key, value in parse_qs(urlparse(base).query).items()}
        params["LAYERS"] = self.layer
        params["TIME"] = timestamp
        return self.endpoint + "?" + urlencode(params)


class Goes19InfraredProvider(Goes19GeoColorProvider):
    """Canal 13 (10,3 µm): cobertura de nuvens de dia e de noite."""

    layer = "GOES-East_ABI_Band13_Clean_Infrared"

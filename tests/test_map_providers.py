from astropanel.services.map_providers import Goes19GeoColorProvider, Goes19InfraredProvider, NasaGibsProvider, MAP_PROVIDERS
from astropanel.services.map_providers import weather_web_url
from urllib.parse import parse_qs, urlparse


def test_nasa_gibs_url_uses_wms_and_coordinates() -> None:
    url = NasaGibsProvider().build_url(-23.55, -46.63, 7, 640, 300)
    assert "gibs.earthdata.nasa.gov" in url
    assert "MODIS_Terra_CorrectedReflectance_TrueColor" in url
    assert "BBOX=" in url


def test_goes_georeferenced_layers_use_latest_metadata_and_observatory():
    capabilities = '<WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability>'
    for provider in (Goes19GeoColorProvider(), Goes19InfraredProvider()):
        capabilities += f'<Layer><Name>{provider.layer}</Name><Dimension name="time" default="2026-10-10T08:20:00Z"/></Layer>'
    capabilities += '</Capability></WMS_Capabilities>'
    for provider in (Goes19GeoColorProvider(), Goes19InfraredProvider()):
        time = provider.latest_time(capabilities)
        assert time == "2026-10-10T08:20:00Z"
        query = parse_qs(urlparse(provider.image_url(time, -19.9167, -43.9345, 7, 640, 300)).query)
        assert query["LAYERS"] == [provider.layer]
        assert query["TIME"] == [time]
        assert query["CRS"] == ["EPSG:4326"]
        assert provider.project_location(-19.9167, -43.9345) == (0.5, 0.5)
    assert Goes19GeoColorProvider.latest_time('<invalid') is None
    assert Goes19GeoColorProvider.latest_time('<empty/>') is None


def test_windy_web_maps_use_correct_layer_and_observatory():
    for key in ("clouds", "lclouds", "mclouds", "hclouds"):
        url = weather_web_url("windy_" + key, -19.9, -43.9)
        parsed = urlparse(url)
        assert parsed.hostname == "embed.windy.com"
        query = parse_qs(parsed.query)
        assert query["overlay"] == [key]
        assert query["lat"] == ["-19.9"]
        assert query["lon"] == ["-43.9"]
        assert query["detailLat"] == ["-19.9"]
        assert query["detailLon"] == ["-43.9"]
        assert "key" not in query
    assert weather_web_url("instarain", 0, 0) == "https://www.instarain.com.br/"
    assert weather_web_url("goes19_geocolor", 0, 0) == ""


def test_new_web_maps_start_at_observatory():
    light = urlparse(weather_web_url("light_pollution", -19.9, -43.9))
    assert light.hostname == "www.lightpollutionmap.info"
    assert parse_qs(light.fragment)["lat"] == ["-19.9"]
    assert parse_qs(light.fragment)["lon"] == ["-43.9"]
    ventusky = urlparse(weather_web_url("ventusky", -19.9, -43.9))
    assert ventusky.hostname == "www.ventusky.com"
    assert parse_qs(ventusky.query)["p"] == ["-19.9;-43.9;7"]
    assert parse_qs(ventusky.query)["l"] == ["clouds-total"]
    assert parse_qs(ventusky.query)["pin"] == ["-19.9;-43.9;dot;Observador"]
    assert "windy_rain" not in MAP_PROVIDERS
    assert "windy_wind" not in MAP_PROVIDERS


def test_combined_map_uses_windy_clouds_and_observer_marker():
    url = weather_web_url("windy_instarain", -23.55, -46.63)
    query = parse_qs(urlparse(url).query)
    assert query["overlay"] == ["clouds"]
    assert query["detailLat"] == ["-23.55"]
    assert query["detailLon"] == ["-46.63"]
    assert "windy_instarain" in MAP_PROVIDERS


def test_light_pollution_uses_custom_observer_instead_of_native_numbered_pin():
    query = parse_qs(urlparse(weather_web_url('light_pollution', -23.55, -46.63)).fragment)
    assert query['lat'] == ['-23.55']
    assert query['lon'] == ['-46.63']
    assert 'state' not in query


def test_nasa_observer_projection_matches_requested_bounds():
    for latitude, longitude in ((-19.9167, -43.9345), (-23.55, -46.63), (89, 179)):
        bounds = parse_qs(urlparse(NasaGibsProvider().build_url(latitude, longitude, 7, 640, 300)).query)["BBOX"][0]
        min_lat, min_lon, max_lat, max_lon = map(float, bounds.split(','))
        x, y = NasaGibsProvider.project_location(latitude, longitude)
        assert abs((min_lon + x * (max_lon - min_lon)) - longitude) < 1e-9
        assert abs((max_lat - y * (max_lat - min_lat)) - latitude) < 1e-9



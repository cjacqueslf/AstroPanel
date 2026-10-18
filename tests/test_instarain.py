import re

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QJSEngine
from astropanel.domain.models import ObservatoryLocation
from astropanel.services.instarain import normalize_stations, InstaRainClient
from astropanel.ui.instarain import map_html


def test_only_public_stations_with_valid_coordinates_are_drawn():
    rows = [dict(Id=1, Nome='Estação', Latitude='-23.5', Longitude='-46.6', Temperatura=22, Ultimas24h=4),
            dict(Id=2, Publico=False, Latitude=0, Longitude=0),
            dict(Id=3, Latitude=None, Longitude=0),
            dict(Id=4, Latitude='nan', Longitude=0),
            dict(Id=5, Latitude=91, Longitude=0),
            dict(Id=6, Latitude='invalid', Longitude=0)]
    stations = normalize_stations(rows)
    assert len(stations) == 1
    assert stations[0]['latitude'] == -23.5
    assert stations[0]['name'] == 'Estação'
    assert stations[0]['temperature'] == 22
    assert stations[0]['rain24h'] == 4
    with pytest.raises(ValueError):
        normalize_stations({'error':'unavailable'})


@pytest.mark.parametrize('enabled', [True, False])
def test_map_label_obeys_settings_and_does_not_include_coordinates(enabled):
    app = QApplication.instance() or QApplication([])
    engine = QJSEngine()
    engine.evaluate('''
        var tooltip=null, marker={addTo:function(){return this;},bindTooltip:text=>tooltip=text.textContent};
        var window={addEventListener:()=>{}};
        var document={createElement:()=>({})};
        var map={setView:function(){return this;}};
        var L={map:()=>map,tileLayer:()=>({addTo:()=>{}}),circleMarker:()=>marker};
    ''')
    html = map_html(ObservatoryLocation(map_label='Meu observatório </script>', show_map_label=enabled))
    script = re.findall(r'<script>(.*?)</script>', html, re.S)[0]
    result = engine.evaluate(script)
    assert not result.isError(), result.toString()
    assert engine.evaluate('tooltip').toVariant() == ('Meu observatório </script>' if enabled else None)


def test_client_uses_open_authorization_and_station_api(monkeypatch):
    app = QApplication.instance() or QApplication([])
    client = InstaRainClient()
    requests = []
    monkeypatch.setattr(client, '_request', lambda path, callback, token=None: requests.append((path, callback, token)))
    result = []
    client.ready.connect(result.append)
    client.refresh()
    path, authorize, token = requests.pop()
    assert path == '/oauth/authorize?app=web'
    assert token is None
    authorize({'access_token':'test-public-token'})
    path, receive, token = requests.pop()
    assert path == '/InstaRainApi/v1/meteorologicas?Online=True'
    assert token == 'test-public-token'
    receive([dict(Id=1, Latitude=-23, Longitude=-46, Nome='Estação')])
    assert result[0][0]['name'] == 'Estação'

@pytest.mark.parametrize('weather,icon', [(0,'Blue'),(2,'Blue'),(3,'Blue2'),(4,'Gray'),(5,'Yellow'),(6,'Yellow'),(7,'Orange'),(8,'Red'),(9,'Red')])
def test_original_icons_and_complete_legend(weather, icon):
    from astropanel.ui.combined_weather import overlay_script
    app = QApplication.instance() or QApplication([])
    engine = QJSEngine()
    engine.evaluate('''
        var icons=[], legendCount=0, legendLabels=[];
        function element(tag) {return {style:{},setAttribute:()=>{},appendChild:function(child){
            if(tag==='div' && child.textContent)legendLabels.push(child.textContent);},cloneNode:function(){return this;}};}
        var document={createElement:element};
        var map={_loaded:true,getPane:()=>({}),removeLayer:()=>{}};
        var window={astroInstaMap:map};
        function layer(){return {bindPopup:function(){return this;},bindTooltip:function(){return this;},addTo:function(){return this;}};}
        var L={layerGroup:layer,circle:layer,icon:options=>options,
            marker:(point,options)=>{icons.push(options.icon.iconUrl);return layer();},
            control:()=>({addTo:function(){legendCount++;this.onAdd();return this;}}),
            DomEvent:{disableClickPropagation:()=>{},disableScrollPropagation:()=>{}}};
    ''')
    script = overlay_script([dict(latitude=-23, longitude=-46, weather=weather, name='Estação')])
    result = engine.evaluate(script)
    assert not result.isError(), result.toString()
    assert result.toBool()
    assert engine.evaluate('icons[0]').toString() == f'https://www.instarain.com.br/web/mapa/{icon}.png'
    assert engine.evaluate('legendLabels').toVariant()[:7] == ['InstaRain · condições', 'Céu limpo', 'Parcialmente nublado',
                                                         'Nublado', 'Chuva fraca', 'Chuva moderada', 'Chuva forte']
    engine.evaluate(script)
    assert engine.evaluate('legendCount').toInt() == 1

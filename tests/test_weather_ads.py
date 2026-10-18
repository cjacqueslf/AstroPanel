from astropanel.ui.weather_ads import block_map_ad


def test_light_pollution_ads_blocked_without_blocking_map_data():
    site = "www.lightpollutionmap.info"
    assert block_map_ad("cdn.fuseplatform.net", "/publift/tags/2/3834/fuse.js", site)
    assert block_map_ad(site, "/assets/lib/ad_prebid.js", site)
    assert block_map_ad("pagead2.googlesyndication.com", "/pagead/js/adsbygoogle.js", site)
    for host, path in ((site, "/assets/index-C1OWRByr.js"),
                       ("tiles.lightpollutionmap.info", "/tiles/sb/7/45/65.png"),
                       ("mt.google.com", "/vt")):
        assert not block_map_ad(host, path, site)


def test_ad_filter_is_scoped_to_light_pollution_map():
    assert not block_map_ad("cdn.fuseplatform.net", "/fuse.js", "embed.windy.com")
    assert not block_map_ad("cdn.fuseplatform.net", "/fuse.js", "www.instarain.com.br")
    assert not block_map_ad("cdn.fuseplatform.net", "/fuse.js", "lightpollutionmap.info.evil.example")


def test_light_pollution_marker_uses_name_permission_and_map_projection():
    from dataclasses import replace
    from PySide6.QtWidgets import QApplication
    from PySide6.QtQml import QJSEngine
    from astropanel.domain.models import ObservatoryLocation
    from astropanel.ui.weather_ads import light_pollution_observer_script
    app = QApplication.instance() or QApplication([])
    engine = QJSEngine()
    engine.evaluate('''
        var location={hostname:'www.lightpollutionmap.info',hash:'#zoom=7&lat=-23.5505&lon=-46.6333'};
        var label={style:{}};
        var marker={style:{},querySelector:()=>label};
        var map={clientWidth:1000,clientHeight:700,addEventListener:()=>{}};
        var document={getElementById:id=>id==='map'?map:marker};
        var window={addEventListener:()=>{}};
        var history={replaceState:(data,title,url)=>location.hash=url};
        function URLSearchParams(value){
            const values={};value.split('&').forEach(part=>{const pair=part.split('=');values[pair[0]]=pair[1];});
            this.get=key=>values[key];this.has=key=>key in values;
        }
    ''')
    location = ObservatoryLocation(map_label='Observatório')
    result = engine.evaluate(light_pollution_observer_script(location))
    assert not result.isError(), result.toString()
    assert result.toBool()
    assert engine.evaluate('marker.style.left').toString() == '500px'
    assert engine.evaluate('marker.style.top').toString() == '350px'
    assert engine.evaluate('label.textContent').toString() == 'Observatório'
    engine.evaluate("history.replaceState(null,'','#zoom=7&lat=-23.5505&lon=-46.5333')")
    assert engine.evaluate('parseFloat(marker.style.left)').toNumber() < 500
    result = engine.evaluate(light_pollution_observer_script(replace(location, show_map_label=False)))
    assert not result.isError(), result.toString()
    assert engine.evaluate('label.style.display').toString() == 'none'
    assert engine.evaluate('label.textContent').toString() == ''

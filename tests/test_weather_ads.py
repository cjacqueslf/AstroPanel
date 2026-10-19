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


def test_embedded_map_disables_site_auto_shrinking_in_small_panels():
    from PySide6.QtWidgets import QApplication
    from astropanel.ui.weather_ads import light_pollution_layout_script
    app = QApplication.instance() or QApplication([])
    script = light_pollution_layout_script().sourceCode()
    assert 'html, body {zoom: 1 !important;}' in script

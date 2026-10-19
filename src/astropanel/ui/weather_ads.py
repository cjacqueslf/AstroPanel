"""Keep the embedded light-pollution map free of advertising."""

from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineScript


def is_light_pollution_host(host: str) -> bool:
    return host == "lightpollutionmap.info" or host.endswith(".lightpollutionmap.info")


def block_map_ad(request_host: str, request_path: str, first_party_host: str) -> bool:
    if not is_light_pollution_host(first_party_host):
        return False
    domains = ("fuseplatform.net", "googlesyndication.com", "doubleclick.net",
               "googletagservices.com", "adnxs.com", "pubmatic.com",
               "rubiconproject.com", "criteo.com", "criteo.net")
    return (any(request_host == domain or request_host.endswith("." + domain)
                for domain in domains)
            or (is_light_pollution_host(request_host)
                and request_path == "/assets/lib/ad_prebid.js"))


class WeatherAdInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()
        if block_map_ad(url.host(), url.path(), info.firstPartyUrl().host()):
            info.block(True)


def light_pollution_layout_script() -> QWebEngineScript:
    script = QWebEngineScript()
    script.setName("AstroPanel light-pollution map without ads")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    script.setSourceCode("""(() => {
        if (location.hostname !== 'www.lightpollutionmap.info' &&
            location.hostname !== 'lightpollutionmap.info') return;
        const style = document.createElement('style');
        style.id = 'astropanel-map-layout';
        style.textContent = `
            html, body {zoom: 1 !important;}
            #leftSidebarContainer, #footerContainer, #RightMenuContainer, [data-fuse] {display: none !important;}
            #leftSidebarContainer {width: 0 !important;}
            #map {left: 0 !important; width: 100% !important; height: 100% !important;}
            #searchCont {left: 10px !important;}
        `;
        document.head.appendChild(style);
        // Let the map recalculate its viewport after the site's own layout.
        window.addEventListener('load', () => window.dispatchEvent(new Event('resize')),
                                {once: true});
    })()""")
    return script


def light_pollution_observer_script(location) -> str:
    """Wait for the native labeled marker's map viewport to be ready."""
    return r"""(() => {
        if (!/^(www\.)?lightpollutionmap\.info$/.test(location.hostname)) return false;
        return !!document.querySelector('#map .ol-viewport');
    })()"""

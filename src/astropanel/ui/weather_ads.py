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
            #leftSidebarContainer, #footerContainer, [data-fuse] {display: none !important;}
            #leftSidebarContainer {width: 0 !important;}
            #map {left: 0 !important; width: 100% !important; height: 100% !important;}
            #RightMenuContainer {max-height: 100% !important;}
            #searchCont {left: 10px !important;}
        `;
        document.head.appendChild(style);
        // Let the map recalculate its viewport after the site's own layout.
        window.addEventListener('load', () => window.dispatchEvent(new Event('resize')),
                                {once: true});
    })()""")
    return script


def light_pollution_observer_script(location) -> str:
    """Project the observer using the site's published Web Mercator view state."""
    import json
    settings = json.dumps(dict(latitude=location.latitude, longitude=location.longitude,
                               label=(location.map_label or location.name) if location.show_map_label else ''),
                          ensure_ascii=True)
    return r"""(() => {
        if (!/^(www\.)?lightpollutionmap\.info$/.test(location.hostname)) return false;
        const map = document.getElementById('map');
        if (!map) return false;
        const config = SETTINGS;
        let marker = document.getElementById('astro-observer');
        if (!marker) {
            marker = document.createElement('div'); marker.id = 'astro-observer';
            marker.style.cssText = 'position:absolute;z-index:500;pointer-events:none;'
                + 'width:12px;height:12px;border:2px solid white;border-radius:50%;'
                + 'background:#e53935;box-sizing:border-box;transform:translate(-50%,-50%)';
            const label = document.createElement('span'); label.className = 'astro-observer-label';
            label.style.cssText = 'position:absolute;bottom:16px;left:50%;transform:translateX(-50%);'
                + 'background:#071019;color:white;padding:3px 6px;border-radius:3px;white-space:nowrap;font:12px Arial';
            marker.appendChild(label); map.appendChild(marker);
        }
        marker._config = config;
        const label = marker.querySelector('span'); label.textContent = config.label;
        label.style.display = config.label ? '' : 'none';
        if (!marker._update) {
            const mercator = (lon, lat) => [6378137*lon*Math.PI/180,
                6378137*Math.log(Math.tan(Math.PI/4+Math.max(-85.05112878,Math.min(85.05112878,lat))*Math.PI/360))];
            marker._update = () => {
                const state = new URLSearchParams(location.hash.slice(1));
                const lat = Number(state.get('lat')), lon = Number(state.get('lon'));
                const zoom = Number(state.get('zoom'));
                if (!state.has('lat') || !state.has('lon') || !state.has('zoom')) return;
                const center = mercator(lon, lat), point = mercator(marker._config.longitude, marker._config.latitude);
                // The site's zoom 0 resolution is 78271.81224932 metres/pixel.
                const resolution = 78271.81224932 / Math.pow(2, zoom);
                const world = 2*Math.PI*6378137;
                let dx = point[0]-center[0]; dx -= Math.round(dx/world)*world;
                marker.style.left = (map.clientWidth/2+dx/resolution)+'px';
                marker.style.top = (map.clientHeight/2-(point[1]-center[1])/resolution)+'px';
                marker.style.visibility = 'visible';
            };
            const replaceState = history.replaceState;
            history.replaceState = function(...args) {
                const result = replaceState.apply(this,args); marker._update(); return result;
            };
            window.addEventListener('hashchange', marker._update);
            window.addEventListener('resize', marker._update);
            let drag = null;
            map.addEventListener('pointerdown', event => {drag=[event.clientX,event.clientY];});
            map.addEventListener('pointermove', event => {
                if (drag && Math.hypot(event.clientX-drag[0],event.clientY-drag[1])>3)
                    marker.style.visibility='hidden';
            });
            window.addEventListener('pointerup', () => {drag=null;});
            map.addEventListener('wheel', () => {marker.style.visibility='hidden';}, {passive:true});
        }
        marker._update(); return true;
    })()""".replace('SETTINGS', settings)

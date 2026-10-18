"""A Leaflet map fed directly by public InstaRain observations."""
import json


def map_html(location):
    config = json.dumps(dict(point=[location.latitude, location.longitude],
                             label=(location.map_label or location.name) if location.show_map_label else ''), ensure_ascii=True).replace('<', '\\u003c')
    return '''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://www.instarain.com.br/pub/@lib/leaflet/leaflet.css">
<style>html,body,#map{height:100%;width:100%;margin:0;background:#15232d}.leaflet-tooltip{font:12px Arial}</style>
</head><body><div id="map"></div>
<script src="https://www.instarain.com.br/pub/@lib/leaflet/leaflet.js"></script>
<script>
const config=CONFIG;
const map=window.astroInstaMap=L.map('map').setView(config.point,7);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
 attribution:'&copy; OpenStreetMap contributors',maxZoom:19}).addTo(map);
const marker=L.circleMarker(config.point,{radius:7,color:'#fff',weight:2,fillColor:'#e53935',fillOpacity:1}).addTo(map);
if(config.label){const text=document.createElement('span');text.textContent=config.label;
 marker.bindTooltip(text,{permanent:true,direction:'top'});}
window.astroObserver=config.point;
window.addEventListener('resize',()=>map.invalidateSize({pan:false}));
</script></body></html>'''.replace('CONFIG', config)


FIT_NEAREST = '''(() => {
 const map=window.astroInstaMap;
 if(!map || !map._astroInstaRain || map._astroStationsFitted) return;
 const points=[];map._astroInstaRain.eachLayer(l=>{if(l.getLatLng)points.push(l.getLatLng());});
 if(!points.length)return;
 const origin=L.latLng(window.astroObserver);
 points.sort((a,b)=>origin.distanceTo(a)-origin.distanceTo(b));
 if(!points.some(p=>map.getBounds().contains(p)))
   map.fitBounds(L.latLngBounds([origin,points[0]]),{padding:[35,35],maxZoom:7,animate:false});
 map._astroStationsFitted=true;
})()'''

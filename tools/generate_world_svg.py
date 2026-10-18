"""Generate a compact bundled world silhouette from Natural Earth's public-domain data.

Requires Cartopy only when regenerating the asset; the application consumes the
resulting SVG directly through Qt and has no Cartopy runtime dependency.
"""
from pathlib import Path

import cartopy.io.shapereader as shpreader


source = shpreader.natural_earth(resolution="110m", category="physical", name="land")
records = shpreader.Reader(source).records()
paths: list[str] = []
for record in records:
    geometry = record.geometry
    polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry]
    for polygon in polygons:
        coords = list(polygon.exterior.coords)
        paths.append("M " + " L ".join(f"{lon + 180:.2f},{90 - lat:.2f}" for lon, lat in coords) + " Z")

svg = """<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 360 180\">
<g fill=\"#6b8b80\" stroke=\"#9db9a9\" stroke-width=\"0.35\">%s</g></svg>""" % "".join(f"<path d=\"{path}\"/>" for path in paths)
target = Path(__file__).parents[1] / "src" / "astropanel" / "resources" / "world_land.svg"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(svg, encoding="utf-8")

"""
Build interactive GeoLibre map with all data layers.

Usage:
  python scripts/visualize_map.py
  python scripts/visualize_map.py --save-only
"""

import json, sys, webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CENTER_WGS84, AOI_BUFFER_KM, AOI_CITY
from geolibre import Map

CLIP_DIR = ROOT / "data" / "etl" / "clipped"
EXCL_DIR = ROOT / "data" / "etl" / "exclusions"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
OUT_DIR = ROOT / "data" / "etl"
CENTER = [AOI_CENTER_WGS84[1], AOI_CENTER_WGS84[0]]


def load(path: Path, label=""):
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if label:
            print(f"  {label}: {len(data.get('features', []))} features")
        return data
    except Exception:
        return {"type": "FeatureCollection", "features": []}


def main():
    prefix = f"{AOI_CITY}_FINLAND"

    fingrid = load(CLIP_DIR / f"{prefix}_fingrid_substations.geojson", "Fingrid")
    power_lines = load(CLIP_DIR / f"{prefix}_osm_power_lines.geojson", "Power lines")
    substations = load(CLIP_DIR / f"{prefix}_osm_substations.geojson", "Substations")
    power_plants = load(CLIP_DIR / f"{prefix}_osm_power_plants.geojson", "Power plants")
    datacenters = load(CLIP_DIR / f"{prefix}_datacentermap.geojson", "Data centers")
    parcels = load(CLIP_DIR / f"{prefix}_mml_land_parcels.geojson", "Land parcels")
    urban = load(CLIP_DIR / f"{prefix}_osm_urban_centers.geojson", "Urban centers")
    natura = load(CLIP_DIR / f"{prefix}_natura2000.geojson", "Natura2000")
    exclusion = load(EXCL_DIR / f"{prefix}_exclusion_zones.geojson", "Exclusions")
    buffer = load(OUT_DIR / f"{prefix}_buffer.geojson", "Buffer")

    m = Map(center=CENTER, zoom=9, basemap="bright", layout="embed", height="700px")

    if buffer["features"]:
        m.add_geojson(buffer, name=f"Buffer ({AOI_BUFFER_KM}km)",
                      strokeColor="#3498db", strokeWidth=2, strokeDash="5,5",
                      fillColor="#3498db", fillOpacity=0.03, popup=["city", "buffer_km"])

    # ── Gradient <8% suitable area (polygonized from tiny mask TIFF) ──
    mask_tif = SUIT_DIR / f"{prefix}_gradient_suitable_8pct.tiff"
    if mask_tif.exists():
        import rasterio
        from rasterio.features import shapes
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union, transform as shp_transform
        import pyproj
        with rasterio.open(mask_tif) as src:
            mask = src.read(1)
            xf = src.transform
        polys = []
        for geom, val in shapes(mask, mask=mask, transform=xf):
            if val == 1:
                polys.append(shape(geom).simplify(5))
        if polys:
            merged = unary_union(polys).simplify(10)
            proj = pyproj.Transformer.from_crs("EPSG:3067", "EPSG:4326", always_xy=True).transform
            merged_wgs84 = shp_transform(proj, merged)
            fc = {"type": "FeatureCollection",
                  "features": [{"type": "Feature", "geometry": mapping(merged_wgs84), "properties": {}}]}
            m.add_geojson(fc, name="Gradient <8%",
                          strokeColor="#90ee90", strokeWidth=0.5,
                          fillColor="#90ee90", fillOpacity=0.4)
            print(f"  Gradient <8%: polygonized from mask TIFF")

    if parcels["features"]:
        m.add_geojson(parcels, name="Land parcels",
                      strokeColor="#8e44ad", strokeWidth=1,
                      fillColor="#8e44ad", fillOpacity=0.05,
                      popup=["kiinteistotunnus", "area_ha"])

    m.add_choropleth(fingrid, column="Kulutus_25", name="Substations (consumption MW)",
                     class_count=5, colormap="YlOrRd", scheme="quantile",
                     circleRadius=10, popup=["SA", "Tyyppi", "Kulutus_25"])

    m.add_geojson(power_lines, name="Power lines", strokeColor="#e74c3c",
                  strokeWidth=2, popup=["voltage", "name", "operator"])
    m.add_geojson(substations, name="Substations (OSM)", strokeColor="#3498db",
                  circleRadius=6, popup=["name", "voltage"])
    m.add_geojson(power_plants, name="Power plants", strokeColor="#2ecc71",
                  circleRadius=8, popup=["name", "generator:source", "plant:source"])

    if datacenters["features"]:
        m.add_geojson(datacenters, name="Data centers", strokeColor="#9b59b6",
                      fillColor="#9b59b6", circleRadius=8,
                      popup=["companyname", "name", "city", "market_mw_live"])
    if urban["features"]:
        m.add_geojson(urban, name="Urban centers", strokeColor="#f39c12",
                      fillColor="#f39c12", fillOpacity=0.5, circleRadius=12,
                      popup=["name", "population"])
    if natura["features"]:
        m.add_geojson(natura, name="Natura2000", strokeColor="#27ae60",
                      fillColor="#27ae60", fillOpacity=0.15, strokeWidth=1,
                      popup=["SITENAME", "SITETYPE", "SITECODE"])
    if exclusion["features"]:
        m.add_geojson(exclusion, name="Exclusion zones", strokeColor="#e74c3c",
                      fillColor="#e74c3c", fillOpacity=0.08, strokeWidth=1,
                      popup=["exclusion_type", "_source_file"])

    html = m.to_html(width="100%", height="700px")
    if not html:
        print("ERROR: map generation failed")
        sys.exit(1)
    out_path = OUT_DIR / f"{prefix}_map.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nSaved: {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")

    if "--save-only" not in sys.argv:
        webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()

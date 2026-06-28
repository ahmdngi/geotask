"""
Visualize all ETL layers using GeoLibre interactive map.

Matches the symbology from the exploration notebook (Chunk 4).
Includes the AOI circular buffer as the base layer.

Usage:
  python scripts/visualize_map.py                    # opens in browser
  python scripts/visualize_map.py --save-only        # just save HTML file
"""

import json
import sys
import webbrowser
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CENTER_WGS84, AOI_BUFFER_KM, AOI_CITY
from geolibre import Map

CLIP_DIR = ROOT / "data" / "etl" / "clipped"
EXCL_DIR = ROOT / "data" / "etl" / "exclusions"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
OUT_DIR = ROOT / "data" / "etl"

# AOI center point (lon, lat — GeoLibre order)
CENTER_LON = AOI_CENTER_WGS84[1]
CENTER_LAT = AOI_CENTER_WGS84[0]


def load_geojson(path: Path, label: str = "") -> dict:
    """Load a GeoJSON from path, return FeatureCollection."""
    if not path.exists():
        if label:
            print(f"  {label}: not found")
        return {"type": "FeatureCollection", "features": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if label:
            print(f"  {label}: {len(data.get('features', []))} features")
        return data
    except Exception as e:
        if label:
            print(f"  {label}: failed to load ({e})")
        return {"type": "FeatureCollection", "features": []}


def main():
    print(f"Building GeoLibre map — {AOI_CITY}")
    print(f"  Center: {CENTER_LAT:.4f}, {CENTER_LON:.4f}  •  Buffer: {AOI_BUFFER_KM}km")
    print()

    # ── Load all layers ──
    fingrid = load_geojson(
        CLIP_DIR / f"{AOI_CITY}_FINLAND_fingrid_substations.geojson",
        "Fingrid substations",
    )
    power_lines = load_geojson(
        CLIP_DIR / f"{AOI_CITY}_FINLAND_osm_power_lines.geojson",
        "Power lines",
    )
    substations = load_geojson(
        CLIP_DIR / f"{AOI_CITY}_FINLAND_osm_substations.geojson",
        "OSM substations",
    )
    power_plants = load_geojson(
        CLIP_DIR / f"{AOI_CITY}_FINLAND_osm_power_plants.geojson",
        "Power plants",
    )
    datacenters = load_geojson(
        CLIP_DIR / f"{AOI_CITY}_FINLAND_datacentermap.geojson",
        "Data centers",
    )
    urban_centers = load_geojson(
        CLIP_DIR / f"{AOI_CITY}_FINLAND_urban_centers.geojson",
        "Urban centers",
    )
    natura2000 = load_geojson(
        CLIP_DIR / f"{AOI_CITY}_FINLAND_natura2000.geojson",
        "Natura2000",
    )
    gradient = load_geojson(
        SUIT_DIR / f"{AOI_CITY}_FINLAND_gradient_lt8.geojson",
        "Gradient <8%",
    )
    exclusion = load_geojson(
        EXCL_DIR / f"{AOI_CITY}_FINLAND_exclusion_zones.geojson",
        "Exclusion zones",
    )
    buffer_layer = load_geojson(
        OUT_DIR / f"{AOI_CITY}_FINLAND_buffer.geojson",
        "AOI buffer",
    )

    # ── Build map ──
    m = Map(
        center=[CENTER_LON, CENTER_LAT],
        zoom=9,
        basemap="bright",
        layout="embed",
        height="700px",
    )

    # 0. AOI circular buffer — base layer, blue dashed outline, very transparent
    if buffer_layer["features"]:
        m.add_geojson(
            buffer_layer,
            name=f"AOI buffer ({AOI_BUFFER_KM}km)",
            strokeColor="#3498db",
            strokeWidth=2,
            strokeDash="5,5",
            fillColor="#3498db",
            fillOpacity=0.03,
            popup=["city", "buffer_km"],
        )

    # 1. Fingrid substations — choropleth on consumption capacity
    m.add_choropleth(
        fingrid,
        column="Kulutus_25",
        name="Fingrid Substations (consumption MW)",
        class_count=5,
        colormap="YlOrRd",
        scheme="quantile",
        circleRadius=10,
        popup=["SA", "Tyyppi", "Kulutus_25"],
    )

    # 2. Power lines — red (#e74c3c)
    m.add_geojson(
        power_lines,
        name="Power lines (110-400kV OSM)",
        strokeColor="#e74c3c",
        strokeWidth=2,
        popup=["voltage", "name", "operator"],
    )

    # 3. OSM substations — blue (#3498db)
    m.add_geojson(
        substations,
        name="Substations (OSM)",
        strokeColor="#3498db",
        circleRadius=6,
        popup=["name", "voltage"],
    )

    # 4. Power plants — green (#2ecc71)
    m.add_geojson(
        power_plants,
        name="Power plants (OSM)",
        strokeColor="#2ecc71",
        circleRadius=8,
        popup=["name", "generator:source", "plant:source"],
    )

    # 5. Data centers — purple (#9b59b6)
    if datacenters["features"]:
        m.add_geojson(
            datacenters,
            name="Data Center Map (verified)",
            strokeColor="#9b59b6",
            fillColor="#9b59b6",
            circleRadius=8,
            popup=["companyname", "name", "city", "market_mw_live"],
        )

    # 6. Urban centers — orange (#f39c12), circle, 50% fill
    if urban_centers["features"]:
        m.add_geojson(
            urban_centers,
            name="Urban centers (100k+)",
            strokeColor="#f39c12",
            fillColor="#f39c12",
            fillOpacity=0.5,
            circleRadius=12,
            popup=["name", "population"],
        )

    # 7. Natura2000 — green (#27ae60), transparent fill
    if natura2000["features"]:
        m.add_geojson(
            natura2000,
            name="Natura2000 sites",
            strokeColor="#27ae60",
            fillColor="#27ae60",
            fillOpacity=0.15,
            strokeWidth=1,
            popup=["SITENAME", "SITETYPE", "SITECODE"],
        )

    # 8. Gradient suitable (<8%) — green (#2ecc71), very transparent
    if gradient["features"]:
        m.add_geojson(
            gradient,
            name="Gradient suitable (<8%)",
            strokeColor="#2ecc71",
            fillColor="#2ecc71",
            fillOpacity=0.1,
            strokeWidth=0.5,
        )

    # 9. Exclusion zones — red (#e74c3c), very transparent
    if exclusion["features"]:
        m.add_geojson(
            exclusion,
            name="Exclusion zones (fatal flaws)",
            strokeColor="#e74c3c",
            fillColor="#e74c3c",
            fillOpacity=0.08,
            strokeWidth=1,
            popup=["exclusion_type", "_source_file"],
        )

    # ── Save ──
    html_map = m.to_html(width="100%", height="700px")
    out_path = OUT_DIR / f"{AOI_CITY}_FINLAND_map.html"
    out_path.write_text(html_map, encoding="utf-8")
    print(f"\n✅ Map saved: {out_path}")

    save_only = "--save-only" in sys.argv
    if not save_only:
        webbrowser.open(out_path.as_uri())
        print("  Opened in browser")

    size_kb = out_path.stat().st_size / 1024
    print(f"  File size: {size_kb:.0f} KB")


if __name__ == "__main__":
    main()

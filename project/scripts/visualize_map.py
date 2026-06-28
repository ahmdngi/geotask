"""
Visualize all ETL layers using GeoLibre interactive map.

Loads clipped + exclusion + suitability layers and renders an HTML map.
Opens in browser automatically when run standalone.

Usage:
  python scripts/visualize_map.py                    # opens in browser
  python scripts/visualize_map.py --save-only        # just save HTML file
"""

import json
import sys
import webbrowser
from pathlib import Path

import geopandas as gpd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY
from geolibre import Map

CLIP_DIR = ROOT / "data" / "etl" / "clipped"
EXCL_DIR = ROOT / "data" / "etl" / "exclusions"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
OUT_DIR = ROOT / "data" / "etl"

# AOI center point
CENTER_LAT = (AOI_BBOX_WGS84[0] + AOI_BBOX_WGS84[2]) / 2
CENTER_LON = (AOI_BBOX_WGS84[1] + AOI_BBOX_WGS84[3]) / 2


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
    except Exception:
        if label:
            print(f"  {label}: failed to load")
        return {"type": "FeatureCollection", "features": []}


def main():
    print(f"Building GeoLibre map — {AOI_CITY}")
    print(f"  Center: {CENTER_LAT:.4f}, {CENTER_LON:.4f}")
    print(f"  Loading layers from: {CLIP_DIR}")
    print()

    # ── Load all layers ──
    layers = {
        "fingrid_substations": load_geojson(
            CLIP_DIR / f"{AOI_CITY}_FINLAND_fingrid_substations.geojson",
        ),
        "power_lines": load_geojson(
            CLIP_DIR / f"{AOI_CITY}_FINLAND_osm_power_lines.geojson",
        ),
        "substations": load_geojson(
            CLIP_DIR / f"{AOI_CITY}_FINLAND_osm_substations.geojson",
        ),
        "power_plants": load_geojson(
            CLIP_DIR / f"{AOI_CITY}_FINLAND_osm_power_plants.geojson",
        ),
        "urban_centers": load_geojson(
            CLIP_DIR / f"{AOI_CITY}_FINLAND_urban_centers.geojson",
        ),
        "datacenters": load_geojson(
            CLIP_DIR / f"{AOI_CITY}_FINLAND_datacentermap.geojson",
        ),
        "natura2000": load_geojson(
            CLIP_DIR / f"{AOI_CITY}_FINLAND_natura2000.geojson",
        ),
    }

    # Exclusion zones (from merge_exclusions.py)
    exclusion = load_geojson(
        EXCL_DIR / f"{AOI_CITY}_FINLAND_exclusion_zones.geojson",
    )

    # Gradient suitability (from compute_gradient.py)
    gradient = load_geojson(
        SUIT_DIR / f"{AOI_CITY}_FINLAND_gradient_lt8.geojson",
    )

    # ── Build map ──
    m = Map(
        center=[CENTER_LON, CENTER_LAT],
        zoom=9,
        basemap="bright",
        layout="embed",
        height="700px",
    )

    # 1. Fingrid substations
    m.add_choropleth(
        layers["fingrid_substations"],
        column="Kulutus_25",
        name="Fingrid Substations (consumption MW)",
        class_count=5,
        colormap="YlOrRd",
        scheme="quantile",
        circleRadius=10,
        popup=["SA", "Tyyppi", "Kulutus_25"],
    )

    # 2. Power lines
    m.add_geojson(
        layers["power_lines"],
        name="Power lines (110-400kV OSM)",
        strokeColor="#e74c3c",
        strokeWidth=2,
        popup=["voltage", "name", "operator"],
    )

    # 3. OSM substations
    m.add_geojson(
        layers["substations"],
        name="Substations (OSM)",
        strokeColor="#3498db",
        circleRadius=6,
        popup=["name", "voltage"],
    )

    # 4. Power plants
    m.add_geojson(
        layers["power_plants"],
        name="Power plants (OSM)",
        strokeColor="#2ecc71",
        circleRadius=8,
        popup=["name", "generator:source", "plant:source"],
    )

    # 5. Data centers
    if layers["datacenters"]["features"]:
        m.add_geojson(
            layers["datacenters"],
            name="Data Center Map (verified)",
            strokeColor="#9b59b6",
            fillColor="#9b59b6",
            circleRadius=8,
            popup=["companyname", "name", "city"],
        )

    # 6. Urban centers
    if layers["urban_centers"]["features"]:
        m.add_geojson(
            layers["urban_centers"],
            name="Urban centers (100k+)",
            strokeColor="#f39c12",
            fillColor="#f39c12",
            fillOpacity=0.5,
            circleRadius=12,
            popup=["name", "population"],
        )

    # 7. Natura2000
    if layers["natura2000"]["features"]:
        m.add_geojson(
            layers["natura2000"],
            name="Natura2000 sites",
            strokeColor="#27ae60",
            fillColor="#27ae60",
            fillOpacity=0.15,
            strokeWidth=1,
            popup=["SITENAME", "SITETYPE"],
        )

    # 8. Gradient suitable (<8%)
    if gradient["features"]:
        m.add_geojson(
            gradient,
            name="Gradient suitable (<8%)",
            strokeColor="#2ecc71",
            fillColor="#2ecc71",
            fillOpacity=0.1,
            strokeWidth=0.5,
        )

    # 9. Exclusion zones
    if exclusion["features"]:
        m.add_geojson(
            exclusion,
            name="Exclusion zones",
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
    else:
        print("  Use --save-only to skip browser open")

    print(f"  File size: {out_path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

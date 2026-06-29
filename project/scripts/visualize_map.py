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


def load(path: Path, label="") -> dict:
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if label:
            print(f"  {label}: {len(data.get('features', []))} features")
        return data
    except Exception:
        return {"type": "FeatureCollection", "features": []}


def split_by_field(fc: dict, field: str, parse_num=str) -> tuple[dict, dict]:
    """Split a FeatureCollection into two: features WITH a parseable field value, and those WITHOUT."""
    has_val, no_val = [], []
    for f in fc.get("features", []):
        v = f.get("properties", {}).get(field)
        if v is not None and str(v).strip():
            try:
                f["properties"][f"_num"] = float(parse_num(v))
                has_val.append(f)
            except (ValueError, TypeError):
                no_val.append(f)
        else:
            no_val.append(f)
    return ({"type": "FeatureCollection", "features": has_val},
            {"type": "FeatureCollection", "features": no_val})


def max_voltage(v: str) -> float:
    """Parse '400000;110000' → max value."""
    return max(float(x) for x in str(v).replace(" ", "").split(";") if x)


def main():
    prefix = f"{AOI_CITY}_FINLAND"

    fingrid = load(CLIP_DIR / f"{prefix}_fingrid_substations.geojson", "Fingrid")
    power_lines = load(CLIP_DIR / f"{prefix}_osm_power_lines.geojson", "Power lines")
    substations = load(CLIP_DIR / f"{prefix}_osm_substations.geojson", "Substations")
    power_plants = load(CLIP_DIR / f"{prefix}_osm_power_plants.geojson", "Power plants")
    datacenters = load(CLIP_DIR / f"{prefix}_datacentermap.geojson", "Data centers")
    parcels = load(CLIP_DIR / f"{prefix}_mml_land_parcels.geojson", "Land parcels")
    scored = load(SUIT_DIR / f"{prefix}_scored_parcels.geojson", "Scored parcels")
    urban = load(CLIP_DIR / f"{prefix}_osm_urban_centers.geojson", "Urban centers")
    natura = load(CLIP_DIR / f"{prefix}_natura2000.geojson", "Natura2000")
    exclusion = load(EXCL_DIR / f"{prefix}_exclusion_zones.geojson", "Exclusions")
    buffer = load(OUT_DIR / f"{prefix}_buffer.geojson", "Buffer")

    # Split OSM substations: those with voltage → choropleth
    sub_has, _ = split_by_field(substations, "voltage", max_voltage)

    # Split power plants: those with output → choropleth
    pp_has, _ = split_by_field(power_plants, "generator:output:electricity", float)

    m = Map(center=CENTER, zoom=9, basemap="bright", layout="embed", height="700px")

    if buffer["features"]:
        m.add_geojson(buffer, name=f"Buffer ({AOI_BUFFER_KM}km)",
                      strokeColor="#3498db", strokeWidth=2, strokeDash="5,5",
                      fillColor="#3498db", fillOpacity=0.03, popup=["city", "buffer_km"])

    # ── Scored parcels (MCDM choropleth) ──
    if scored["features"]:
        m.add_choropleth(scored, column="mcdm_score", name="Parcel score (MCDM)",
                         class_count=5, colormap="Greens", scheme="quantile",
                         fillOpacity=0.5, strokeColor="#2d7d2d", strokeWidth=0.5,
                         popup=["kiinteistotunnus", "mcdm_score", "area_ha",
                                "score_grid", "score_hv", "score_urban",
                                "score_dc", "score_gen", "score_size"])
    elif parcels["features"]:
        m.add_geojson(parcels, name="Land parcels",
                      strokeColor="#8e44ad", strokeWidth=1,
                      fillColor="#8e44ad", fillOpacity=0.05,
                      popup=["kiinteistotunnus", "area_ha"])

    # ── Fingrid substations — green intensity by MW headroom ──
    m.add_choropleth(fingrid, column="Kulutus_25", name="Fingrid substations (MW)",
                     class_count=5, colormap="Greens", scheme="quantile",
                     circleRadius=12, textField="{Kulutus_25} MW", textSize=10,
                     textColor="#006400", textHaloColor="#fff", textHaloWidth=1,
                     popup=["SA", "Tyyppi", "Kulutus_25"])

    # ── OSM substations with voltage → green intensity by kV level ──
    if sub_has["features"]:
        m.add_choropleth(sub_has, column="_num", name="Substations (OSM) by voltage",
                         class_count=5, colormap="Greens", scheme="quantile",
                         circleRadius=8, textField="{voltage}", textSize=9,
                         textColor="#006400", textHaloColor="#fff", textHaloWidth=1,
                         popup=["name", "voltage"])

    # ── Power lines ──
    m.add_geojson(power_lines, name="Power lines", strokeColor="#e74c3c",
                  strokeWidth=2, popup=["voltage", "name", "operator"])

    # ── Power plants with output → green intensity by MW ──
    if pp_has["features"]:
        m.add_choropleth(pp_has, column="_num", name="Power plants by output (MW)",
                         class_count=5, colormap="Greens", scheme="quantile",
                         circleRadius=10, textField="{generator:output:electricity}",
                         textSize=9, textColor="#006400", textHaloColor="#fff",
                         textHaloWidth=1,
                         popup=["name", "generator:source", "generator:output:electricity"])

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

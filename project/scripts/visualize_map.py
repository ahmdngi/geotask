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
FINAL_DIR = ROOT / "outputs"
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
    candidates = load(FINAL_DIR / "candidates.geojson", "Top candidates")

    # Split OSM substations: those with voltage → choropleth
    sub_has, _ = split_by_field(substations, "voltage", max_voltage)

    # Split power plants: those with output → choropleth
    pp_has, _ = split_by_field(power_plants, "generator:output:electricity", float)

    m = Map(center=CENTER, zoom=9, basemap="positron", layout="embed", height="720px")

    # ── AOI buffer outline ──
    if buffer["features"]:
        m.add_geojson(buffer, name=f"AOI ({AOI_BUFFER_KM} km)",
                      strokeColor="#2c3e50", strokeWidth=2, strokeDash="6,4",
                      fillColor="#2c3e50", fillOpacity=0.02, popup=["city", "buffer_km"])

    # ── Exclusion zones (fatal-flaw) — hatched red, drawn under parcels ──
    if exclusion["features"]:
        m.add_geojson(exclusion, name="Exclusion zones (fatal flaw)",
                      strokeColor="#c0392b", fillColor="#e74c3c", fillOpacity=0.18,
                      strokeWidth=1, popup=["exclusion_type", "_source_file"])
    if natura["features"]:
        m.add_geojson(natura, name="Natura 2000", strokeColor="#16a085",
                      fillColor="#1abc9c", fillOpacity=0.12, strokeWidth=1,
                      popup=["SITENAME", "SITETYPE", "SITECODE"])

    # ── Scored parcels: graduated by MCDM score (viridis) ──
    smin, smax = 4.8, 7.9
    if scored["features"]:
        vals = [f["properties"].get("mcdm_score") for f in scored["features"]
                if f["properties"].get("mcdm_score") is not None]
        if vals:
            smin, smax = min(vals), max(vals)
        m.add_choropleth(scored, column="mcdm_score", name="Parcel score (MCDM)",
                         class_count=5, colormap="viridis", scheme="quantile",
                         fillOpacity=0.55, strokeColor="#555", strokeWidth=0.4,
                         popup=["kiinteistotunnus", "mcdm_score", "area_ha",
                                "score_grid", "score_hv", "score_urban",
                                "score_dc", "score_gen", "score_size"])
    elif parcels["features"]:
        m.add_geojson(parcels, name="Land parcels",
                      strokeColor="#8e44ad", strokeWidth=1,
                      fillColor="#8e44ad", fillOpacity=0.05,
                      popup=["kiinteistotunnus", "area_ha"])

    # ── Grid: power lines (orange) ──
    m.add_geojson(power_lines, name="HV power lines", strokeColor="#e67e22",
                  strokeWidth=2.2, popup=["voltage", "name", "operator"])

    # ── Fingrid substations — blue, MW labelled ──
    m.add_geojson(fingrid, name="Fingrid substations (MW)",
                  strokeColor="#1f4e79", strokeWidth=1.5, fillColor="#2e86c1",
                  circleRadius=12, textField="{Kulutus_25} MW", textSize=10,
                  textColor="#1f4e79", textHaloColor="#fff", textHaloWidth=1.5,
                  popup=["SA", "Tyyppi", "Kulutus_25"])

    # ── OSM substations with voltage (teal) ──
    if sub_has["features"]:
        m.add_geojson(sub_has, name="Substations (OSM)", strokeColor="#0e6655",
                      fillColor="#48c9b0", circleRadius=7, strokeWidth=1,
                      popup=["name", "voltage"])

    # ── Power plants (dark amber) ──
    if pp_has["features"]:
        m.add_geojson(pp_has, name="Power plants", strokeColor="#7d6608",
                      fillColor="#f1c40f", circleRadius=9, strokeWidth=1,
                      popup=["name", "generator:source", "generator:output:electricity"])

    if datacenters["features"]:
        m.add_geojson(datacenters, name="Data centers", strokeColor="#6c3483",
                      fillColor="#9b59b6", circleRadius=8, strokeWidth=1.5,
                      popup=["companyname", "name", "city", "market_mw_live"])
    if urban["features"]:
        m.add_geojson(urban, name="Urban centers", strokeColor="#b9770e",
                      fillColor="#f39c12", fillOpacity=0.6, circleRadius=12,
                      popup=["name", "population"])

    # ── Top-N candidates highlighted on top, labelled ──
    if candidates["features"]:
        m.add_geojson(candidates, name="Top candidates", strokeColor="#111",
                      strokeWidth=2.5, fillColor="#2ecc71", fillOpacity=0.35,
                      textField="#{rank}", textSize=12, textColor="#111",
                      textHaloColor="#fff", textHaloWidth=2,
                      popup=["rank", "kiinteistotunnus", "mcdm_score", "area_ha"])

    # ── Legend + colorbar for non-technical readers ──
    m.add_legend(title="Map key", legend_dict={
        "Top candidate": "#2ecc71",
        "Fingrid substation": "#2e86c1",
        "Substation (OSM)": "#48c9b0",
        "HV power line": "#e67e22",
        "Power plant": "#f1c40f",
        "Data center": "#9b59b6",
        "Urban center": "#f39c12",
        "Exclusion / flood": "#e74c3c",
    }, position="bottom-left")
    m.add_colorbar(colormap="viridis", vmin=round(smin, 1), vmax=round(smax, 1),
                   label="Parcel suitability (MCDM)", position="bottom-right")

    html = m.to_html(width="100%", height="720px",
                     title=f"KRIOS — {AOI_CITY} Data Center Site Suitability")
    if not html:
        print("ERROR: map generation failed")
        sys.exit(1)
    out_path = OUT_DIR / f"{prefix}_map.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nSaved: {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")

    final_path = FINAL_DIR / "final_map.html"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(html, encoding="utf-8")
    print(f"Saved: {final_path}")

    if "--save-only" not in sys.argv:
        webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()

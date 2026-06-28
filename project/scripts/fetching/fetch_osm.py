"""Fetch OSM infrastructure data (power lines, substations, power plants). Output: EPSG:3067 GeoJSON."""

import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import shape

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY, OVERPAST_URL

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
UA = "GIS-Script/1.0"
OSM_BBOX = ",".join(str(v) for v in AOI_BBOX_WGS84)

TARGET_CRS = "EPSG:3067"

LAYERS = {
    "power_lines": {"power": "line"},
    "substations": {"power": "substation"},
    "power_plants": {"power": ["plant", "generator"]},
}


def overpass_query(query: str) -> dict:
    """Run Overpass query with 429 retry, return parsed JSON."""
    url = OVERPAST_URL
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(
                url,
                data={"data": query},
                headers={"User-Agent": UA},
                timeout=300,
            )
        except requests.Timeout:
            print(f"  Request timed out (attempt {attempt+1})")
            if attempt < max_retries:
                continue
            raise
        except requests.RequestException as e:
            print(f"  Request failed: {e}")
            raise

        if r.status_code == 429 and attempt < max_retries:
            wait = 10 * (2**attempt)
            print(f"  Rate limited, retrying in {wait}s...")
            time.sleep(wait)
            continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}: {r.text[:500]}")
        r.raise_for_status()
        try:
            return r.json()
        except json.JSONDecodeError as e:
            print(f"  JSON decode failed: {e}")
            print(f"  Response preview: {r.text[:500]}")
            raise


def element_to_feature(el: dict) -> dict | None:
    """Convert an Overpass element dict to a GeoJSON Feature (WGS84)."""
    if el["type"] == "node":
        geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
    elif el["type"] == "way" and "geometry" in el:
        coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        if len(coords) == 1:
            geom = {"type": "Point", "coordinates": coords[0]}
        else:
            geom = {"type": "LineString" if len(coords) > 1 else "Point", "coordinates": coords}
    else:
        return None
    return {"type": "Feature", "geometry": geom, "properties": el.get("tags", {})}


def classify_element(el: dict) -> list[str]:
    """Return list of layer names this element belongs to."""
    tags = el.get("tags", {})
    labels = []
    power = tags.get("power")
    if power == "line":
        voltage = tags.get("voltage", "")
        if any(v in voltage for v in ("400000", "220000", "110000")):
            labels.append("power_lines")
    if power == "substation":
        labels.append("substations")
    if power in ("plant", "generator"):
        labels.append("power_plants")
    return labels


def save_geojson(features: list[dict], label: str):
    """Save features as GeoJSON reprojected to EPSG:3067."""
    if not features:
        print(f"  No {label} found — skipping save.")
        return

    fc = {"type": "FeatureCollection", "features": features}
    gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
    gdf = gdf.to_crs(TARGET_CRS)

    safe_name = label.replace(" ", "_").replace("/", "_").replace("(", "_").replace(")", "_")
    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_osm_{safe_name}.geojson"

    try:
        gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")
    except Exception as e:
        print(f"  ERROR writing {out_path.name}: {e}")
        import os
        bak = out_path.with_suffix(".bak")
        if out_path.exists():
            os.replace(out_path, bak)
            print(f"  Renamed existing to {bak.name}, retrying...")
            gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")
        else:
            raise

    types = gdf.geometry.geom_type.value_counts().to_dict()
    print(f"  {label}: {len(gdf)} features ({dict(types)}), saved -> {out_path.name}")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    q = (
        f'[out:json][timeout:300][maxsize:1073741824][bbox:{OSM_BBOX}];'
        '('
        '  way["power"="line"]["voltage"~"400000|220000|110000"];'
        '  node["power"="substation"];'
        '  way["power"="substation"];'
        '  node["power"="plant"];'
        '  way["power"="plant"];'
        '  node["power"="generator"];'
        '  way["power"="generator"];'
        ');'
        'out geom;'
    )

    print("Fetching OSM infrastructure (power lines, substations, plants)...")
    data = overpass_query(q)
    elements = data.get("elements", [])
    print(f"  Raw elements: {len(elements)}")

    all_features = {}
    for el in elements:
        feat = element_to_feature(el)
        if feat is None:
            continue
        for label in classify_element(el):
            all_features.setdefault(label, []).append(feat)

    for label in ["power_lines", "substations", "power_plants"]:
        save_geojson(all_features.get(label, []), label)


if __name__ == "__main__":
    main()

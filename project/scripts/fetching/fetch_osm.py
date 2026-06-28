"""
Fetch OSM infrastructure data (power lines, substations, power plants, data centers).

Source: Overpass API (no auth, requires User-Agent)
Native CRS: WGS84 (EPSG:4326)
Output: data/raw/{CITY}_FINLAND_osm_*.geojson (EPSG:3067)
"""

import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
UA = "KRIOS-GIS/1.0 (assignment)"
OSM_BBOX = ",".join(str(v) for v in AOI_BBOX_WGS84)  # min_lat,min_lon,max_lat,max_lon

TARGET_CRS = "EPSG:3067"

LAYERS = {
    "power_lines": {"power": "line"},
    "substations": {"power": "substation"},
    "power_plants": {"power": ["plant", "generator"]},
    "data_centers": {"building": "datacenter", "man_made": "data_center", "office": "it"},
}


def overpass_query(query: str) -> dict:
    """Run Overpass query with 429 retry, return parsed JSON."""
    url = "https://overpass-api.de/api/interpreter"
    max_retries = 3
    for attempt in range(max_retries + 1):
        r = requests.post(
            url,
            data={"data": query},
            headers={"User-Agent": UA},
            timeout=120,
        )
        if r.status_code == 429 and attempt < max_retries:
            wait = 10 * (2**attempt)
            print(f"  Rate limited, retrying in {wait}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()


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
    if (
        tags.get("building") == "datacenter"
        or tags.get("man_made") == "data_center"
        or tags.get("office") == "it"
    ):
        labels.append("data_centers")
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
    gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    types = gdf.geometry.geom_type.value_counts().to_dict()
    print(f"  {label}: {len(gdf)} features ({dict(types)}), saved -> {out_path.name}")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Combined Overpass query – one call for all layers
    q = (
        f'[out:json][timeout:90][bbox:{OSM_BBOX}];'
        '('
        '  way["power"="line"]["voltage"~"400000|220000|110000"];'
        '  node["power"="substation"];'
        '  way["power"="substation"];'
        '  node["power"="plant"];'
        '  way["power"="plant"];'
        '  node["power"="generator"];'
        '  way["power"="generator"];'
        '  node["building"="datacenter"];'
        '  way["building"="datacenter"];'
        '  relation["building"="datacenter"];'
        '  node["man_made"="data_center"];'
        '  way["man_made"="data_center"];'
        '  relation["man_made"="data_center"];'
        '  node["office"="it"];'
        '  way["office"="it"];'
        '  relation["office"="it"];'
        ');'
        'out geom;'
    )

    print("Fetching OSM infrastructure (power lines, substations, plants, data centers)...")
    data = overpass_query(q)
    elements = data.get("elements", [])
    print(f"  Raw elements: {len(elements)}")

    # Convert elements → features
    all_features = {}
    for el in elements:
        feat = element_to_feature(el)
        if feat is None:
            continue
        for label in classify_element(el):
            all_features.setdefault(label, []).append(feat)

    # Save each layer
    for label in ["power_lines", "substations", "power_plants", "data_centers"]:
        save_geojson(all_features.get(label, []), label)


if __name__ == "__main__":
    main()

"""Fetch urban centers (pop >= 100k) from OSM. Output: EPSG:3067 GeoJSON."""

import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY, OVERPAST_URL

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
UA = "GIS-Script/1.0"
OSM_BBOX = ",".join(str(v) for v in AOI_BBOX_WGS84)
TARGET_CRS = "EPSG:3067"


def overpass_query(query: str) -> dict:
    """Run Overpass query with 429 retry, return parsed JSON."""
    url = OVERPAST_URL
    max_retries = 3
    for attempt in range(max_retries + 1):
        r = requests.post(
            url,
            data={"data": query},
            headers={"User-Agent": UA},
            timeout=60,
        )
        if r.status_code == 429 and attempt < max_retries:
            wait = 10 * (2**attempt)
            print(f"  Rate limited, retrying in {wait}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    return {}


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    q = (
        f'[out:json][timeout:60][bbox:{OSM_BBOX}];'
        '('
        '  node["place"~"city|town"]["population"];'
        '  way["place"~"city|town"]["population"];'
        ');'
        'out center;'
    )

    print("Fetching urban centers (population >= 100k)...")
    data = overpass_query(q)
    elements = data.get("elements", [])

    features = []
    for el in elements:
        tags = el.get("tags", {})
        pop_str = str(tags.get("population", "0")).replace(",", "").replace(" ", "")
        try:
            pop = int(pop_str)
        except (ValueError, TypeError):
            continue
        if pop < 100000:
            continue

        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": tags.get("name", "?"),
                "name_fi": tags.get("name:fi", ""),
                "name_sv": tags.get("name:sv", ""),
                "population": pop,
                "place": tags.get("place", ""),
            },
        })

    fc = {"type": "FeatureCollection", "features": features}
    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_osm_urban_centers.geojson"

    if not features:
        print("  No urban centers >= 100k found within AOI.")
        empty_gdf = gpd.GeoDataFrame({"name": [], "population": []}, geometry=[], crs="EPSG:4326")
        empty_gdf = empty_gdf.to_crs(TARGET_CRS)
        empty_gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")
        names = []
        gdf = empty_gdf
    else:
        gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
        gdf = gdf.to_crs(TARGET_CRS)
        gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")
        names = sorted(gdf["name"].tolist())
    print(f"  Urban centers: {len(gdf)}")
    for n in names:
        row = gdf[gdf["name"] == n].iloc[0]
        print(f"    {n} — {int(row['population']):,} people")
    print(f"  CRS:   {TARGET_CRS}")
    print(f"  Saved: {out_path.name}")


if __name__ == "__main__":
    main()

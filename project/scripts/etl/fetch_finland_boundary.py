"""
Fetch Finland national boundary from OSM (admin_level=2).

Source: Overpass API (no auth)
Output: data/etl/finland_boundary.geojson (EPSG:3067)
"""

import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

ETL_DIR = ROOT / "data" / "etl"
TARGET_CRS = "EPSG:3067"
UA = "KRIOS-GIS/1.0 (assignment)"


def main():
    ETL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ETL_DIR / "finland_boundary.geojson"

    if out_path.exists():
        print(f"  Finland boundary already exists — skipping fetch")
        return

    q = (
        '[out:json][timeout:60];'
        'relation["admin_level"="2"]["name"="Finland"];'
        'out geom;'
    )

    print("Fetching Finland boundary from OSM...")
    r = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": q},
        headers={"User-Agent": UA},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    elements = data.get("elements", [])
    print(f"  Found {len(elements)} relations")

    if not elements:
        print("  ERROR: No Finland boundary found")
        sys.exit(1)

    # Convert to GeoJSON
    features = []
    for el in elements:
        if el["type"] != "relation" or "members" not in el:
            continue
        tags = el.get("tags", {})

        # Build geometry from member ways
        coords_list = []
        for member in el.get("members", []):
            if member.get("type") == "way" and "geometry" in member:
                way_coords = [[p["lon"], p["lat"]] for p in member["geometry"]]
                if len(way_coords) >= 4:
                    coords_list.append(way_coords)

        if not coords_list:
            continue

        geom = {
            "type": "MultiPolygon",
            "coordinates": [[c] for c in coords_list],
        }
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "name": tags.get("name", "Finland"),
                "admin_level": tags.get("admin_level"),
                "iso_code": tags.get("ISO3166-1"),
            },
        })

    fc = {"type": "FeatureCollection", "features": features}
    gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
    gdf = gdf.to_crs(TARGET_CRS)

    # Dissolve all boundary parts into single polygon
    dissolved = gdf.dissolve()
    dissolved.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    area_km2 = dissolved.geometry.area.iloc[0] / 1e6
    print(f"  Area:  {area_km2:,.0f} km²")
    print(f"  CRS:   {TARGET_CRS}")
    print(f"  Saved: {out_path.name}")


if __name__ == "__main__":
    main()

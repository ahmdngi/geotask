"""Fetch Fingrid grid substation connection capacity. Output: EPSG:3067 GeoJSON."""

import json
import sys
import time
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY, FINGRID_BASE

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
LAYER_URL = f"{FINGRID_BASE}/Kytkinlaitokset_Fingrid/FeatureServer/0"


def fetch_all_features(url: str, out_fields: str = "*", out_sr: int = 3067) -> list[dict[str, Any]]:
    """Paginate all features from an ArcGIS FeatureServer layer."""
    all_features = []
    offset = 0
    page_size = 2000

    while True:
        resp = requests.get(
            f"{url}/query",
            params={
                "f": "json",
                "where": "1=1",
                "outFields": out_fields,
                "returnGeometry": "true",
                "outSR": out_sr,
                "resultRecordCount": page_size,
                "resultOffset": offset,
                "geometry": f"{AOI_BBOX_WGS84[1]},{AOI_BBOX_WGS84[0]},{AOI_BBOX_WGS84[3]},{AOI_BBOX_WGS84[2]}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        if not features:
            break
        all_features.extend(features)
        offset += len(features)
        time.sleep(0.3)

    return all_features


def main():
    import os
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Fingrid substations (grid capacity)...")
    features = fetch_all_features(LAYER_URL)

    if not features:
        print("No features found in AOI.")
        sys.exit(0)

    tmp = DATA_DIR / "_fingrid_raw.json"
    with open(tmp, "w") as f:
        json.dump({"features": features}, f)

    gdf = gpd.read_file(tmp)
    gdf = gdf.set_crs("EPSG:3067")
    tmp.unlink()

    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_fingrid_substations.geojson"
    gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    print(f"  Features: {len(gdf)}")
    print(f"  CRS:      EPSG:3067 (native)")
    print(f"  Saved:    {out_path.name}")


if __name__ == "__main__":
    main()

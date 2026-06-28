"""Fetch flood hazard zones from SYKE WFS (river + sea, multiple return periods). Output: EPSG:3067 GeoJSON."""

import sys
import time
from pathlib import Path

import geopandas as gpd
import requests
from pyproj import Transformer

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY, SYKE_WFS

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
TARGET_CRS = "EPSG:3067"
MAX_FEATS = 5000

FLOOD_LAYERS = {
    "river_100a": "inspire_nz:NZ.Tulvavaaravyohykkeet_Vesistotulva_1_100a",
    "river_250a": "inspire_nz:NZ.Tulvavaaravyohykkeet_Vesistotulva_1_250a",
    "sea_100a": "inspire_nz:NZ.Tulvavaaravyohykkeet_Meritulva_1_100a",
    "sea_50a": "inspire_nz:NZ.Tulvavaaravyohykkeet_Meritulva_1_50a",
}


def wgs84_to_3067_bbox(wgs84_bbox: list[float]) -> str:
    """Convert [min_lat, min_lon, max_lat, max_lon] to EPSG:3067 bbox string."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    minx, miny = transformer.transform(wgs84_bbox[1], wgs84_bbox[0])
    maxx, maxy = transformer.transform(wgs84_bbox[3], wgs84_bbox[2])
    return f"{minx},{miny},{maxx},{maxy},urn:x-ogc:def:crs:EPSG:3067"


def fetch_syke_wfs(type_name: str, bbox_3067: str) -> list[dict]:
    """Fetch features from SYKE WFS with pagination, capped at MAX_FEATS."""
    ws = type_name.split(":")[0]
    url = f"{SYKE_WFS}/{ws}/wfs"
    all_features = []
    start_idx = 0

    while len(all_features) < MAX_FEATS:
        resp = requests.get(
            url,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": type_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": bbox_3067,
                "count": 1000,
                "startIndex": start_idx,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"  WFS error {resp.status_code} for {type_name}: {resp.text[:200]}")
            break

        features = resp.json().get("features", [])
        if not features:
            break

        all_features.extend(features)
        start_idx += len(features)

        if len(features) < 1000:
            break
        time.sleep(0.5)

    return all_features


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bbox_3067 = wgs84_to_3067_bbox(AOI_BBOX_WGS84)

    for label, type_name in FLOOD_LAYERS.items():
        print(f"Fetching flood_{label}...")
        features = fetch_syke_wfs(type_name, bbox_3067)

        if not features:
            print(f"  No features — skipping.")
            continue

        fc = {"type": "FeatureCollection", "features": features}
        gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
        gdf = gdf.to_crs(TARGET_CRS)

        out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_syke_flood_{label}.geojson"
        gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")

        print(f"  Features: {len(gdf)}")
        if "toistuvuus" in gdf.columns:
            print(f"  Return periods: {gdf['toistuvuus'].value_counts().to_dict()}")
        print(f"  Saved:    {out_path.name}")


if __name__ == "__main__":
    main()

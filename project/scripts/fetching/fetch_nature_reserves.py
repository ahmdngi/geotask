"""Fetch nature reserves and protected areas from SYKE WFS. Output: EPSG:3067 GeoJSON."""

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

RESERVE_LAYERS = {
    "reserves_state": "inspire_ps:PS.ProtectedSitesValtionOmistamaLuonnonsuojelualue",
    "reserves_private": "inspire_ps:PS.ProtectedSitesYksityistenMaillaOlevaLuonnonsuojelualue",
    "reserves_spa": "inspire_ps:PS.ProtectedSitesSpecialProtectionArea",
    "reserves_sac": "inspire_ps:PS.ProtectedSitesSpecialAreaOfConservation",
}


def wgs84_to_3067_bbox(wgs84_bbox: list[float]) -> str:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    minx, miny = transformer.transform(wgs84_bbox[1], wgs84_bbox[0])
    maxx, maxy = transformer.transform(wgs84_bbox[3], wgs84_bbox[2])
    return f"{minx},{miny},{maxx},{maxy},urn:x-ogc:def:crs:EPSG:3067"


def fetch_syke_wfs(type_name: str, bbox_3067: str) -> list[dict]:
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
            print(f"  WFS error {resp.status_code}: {resp.text[:200]}")
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

    for label, type_name in RESERVE_LAYERS.items():
        print(f"Fetching {label}...")
        features = fetch_syke_wfs(type_name, bbox_3067)

        if not features:
            print(f"  No features — skipping.")
            continue

        fc = {"type": "FeatureCollection", "features": features}
        gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
        gdf = gdf.to_crs(TARGET_CRS)

        out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_syke_nature_reserves_{label}.geojson"
        gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")

        print(f"  Features: {len(gdf)}")
        if "tyyppinimi" in gdf.columns:
            print(f"  Types:    {gdf['tyyppinimi'].value_counts().to_dict()}")
        print(f"  Saved:    {out_path.name}")


if __name__ == "__main__":
    main()

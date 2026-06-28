"""Fetch Natura 2000 protected sites from EEA ArcGIS REST (all 3 layers). Output: EPSG:3067 GeoJSON."""

import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY, EEA_NATURA

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
TARGET_CRS = "EPSG:3067"

BASE_URL = EEA_NATURA.rsplit("/", 1)[0]

LAYERS = {
    0: "Habitats Directive",
    1: "Birds Directive",
    2: "Habitats + Birds",
}


def fetch_natura_layer(layer_id: int, bbox_wgs84: list[float]) -> list[dict]:
    """Fetch all features from one Natura 2000 MapServer layer with pagination."""
    nat_bbox = f"{bbox_wgs84[1]},{bbox_wgs84[0]},{bbox_wgs84[3]},{bbox_wgs84[2]}"
    url = f"{BASE_URL}/{layer_id}"
    all_features = []
    offset = 0
    page_size = 1000

    while True:
        resp = requests.get(
            f"{url}/query",
            params={
                "f": "geojson",
                "where": "SITECODE LIKE 'FI%'",
                "outFields": "SITECODE,SITENAME,SITETYPE,Area_ha",
                "outSR": 4326,
                "returnGeometry": "true",
                "geometry": nat_bbox,
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "resultRecordCount": page_size,
                "resultOffset": offset,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  Layer {layer_id} returned {resp.status_code}: {resp.text[:200]}")
            break
        features = resp.json().get("features", [])
        if not features:
            break
        for feat in features:
            feat["properties"]["natura_layer"] = LAYERS.get(layer_id, str(layer_id))
        all_features.extend(features)
        offset += len(features)
        time.sleep(0.3)

    return all_features


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Natura 2000 sites (all 3 layers)...")
    all_features = []
    for layer_id in sorted(LAYERS):
        print(f"  Layer {layer_id} ({LAYERS[layer_id]})...")
        feats = fetch_natura_layer(layer_id, AOI_BBOX_WGS84)
        print(f"    Features: {len(feats)}")
        all_features.extend(feats)

    if not all_features:
        print("  No Natura 2000 sites intersecting AOI.")
        return

    fc = {"type": "FeatureCollection", "features": all_features}
    gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
    gdf = gdf.to_crs(TARGET_CRS)

    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_eea_natura2000.geojson"
    gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    total_area = gdf["Area_ha"].sum() if "Area_ha" in gdf.columns else 0
    layer_counts = gdf["natura_layer"].value_counts().to_dict() if "natura_layer" in gdf.columns else {}

    print(f"  Total sites: {len(gdf)}")
    print(f"  Per layer:   {layer_counts}")
    print(f"  Total area:  {total_area:,.0f} ha")
    print(f"  CRS:         {TARGET_CRS}")
    print(f"  Saved:       {out_path.name}")


if __name__ == "__main__":
    main()

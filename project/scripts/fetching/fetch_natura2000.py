"""
Fetch Natura 2000 protected sites from EEA ArcGIS REST.

Source: EEA ArcGIS REST (no auth)
Native CRS: WGS84 (EPSG:4326)
Output: data/raw/{CITY}_FINLAND_natura2000.geojson (EPSG:3067)

Note: No filtering — returns all sites intersecting the AOI bbox.
"""

import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests
import sys
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
TARGET_CRS = "EPSG:3067"

MAP_SERVER_URL = (
    "https://bio.discomap.eea.europa.eu/arcgis/rest/services"
    "/ProtectedSites/Natura2000Sites/MapServer/0"
)


def fetch_natura_bbox(
    bbox_wgs84: list[float], sitetype: int = 0
) -> list[dict]:
    """Fetch Natura 2000 sites intersecting bbox via ArcGIS REST.

    bbox_wgs84: [min_lat, min_lon, max_lat, max_lon]
    sitetype: 0=Habitats, 1=Birds, 2=Both
    """
    # Convert lat-lon → lon-lat for ArcGIS envelope
    nat_bbox = f"{bbox_wgs84[1]},{bbox_wgs84[0]},{bbox_wgs84[3]},{bbox_wgs84[2]}"

    all_features = []
    offset = 0
    page_size = 1000

    while True:
        resp = requests.get(
            f"{MAP_SERVER_URL}/query",
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
            print(f"  ArcGIS returned {resp.status_code}: {resp.text[:200]}")
            break
        features = resp.json().get("features", [])
        if not features:
            break
        all_features.extend(features)
        offset += len(features)
        time.sleep(0.3)

    return all_features


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Natura 2000 sites...")
    features = fetch_natura_bbox(AOI_BBOX_WGS84)

    if not features:
        print("  No Natura 2000 sites intersecting AOI.")
        sys.exit(0)

    fc = {"type": "FeatureCollection", "features": features}
    gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
    gdf = gdf.to_crs(TARGET_CRS)

    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_natura2000.geojson"
    gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    site_types = gdf["SITETYPE"].value_counts().to_dict() if "SITETYPE" in gdf.columns else {}
    total_area = gdf["Area_ha"].sum() if "Area_ha" in gdf.columns else 0

    print(f"  Sites:    {len(gdf)}")
    print(f"  Types:    {site_types}")
    print(f"  Area:     {total_area:,.0f} ha")
    print(f"  CRS:      {TARGET_CRS}")
    print(f"  Saved:    {out_path.name}")


if __name__ == "__main__":
    main()

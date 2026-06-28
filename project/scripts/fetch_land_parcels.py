"""
Fetch land parcels (kiinteistöt) from MML OGC API Features.

Source: MML OGC API Features (requires MML_KEY in config/keys.json)
Native CRS: WGS84 by default, request EPSG:3067 for metric geometry
Output: data/raw/{CITY}_FINLAND_land_parcels.geojson (EPSG:3067)

Note: MML parcels at 100km radius can be GB-scale. The script fetches
      parcels intersecting the AOI bbox and saves all results without
      filtering. Set MML_KEY in config/keys.json before running.
"""

import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from scripts.config import AOI_BBOX_WGS84, AOI_CITY, MML_KEY

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TARGET_CRS = "EPSG:3067"
PAGE_LIMIT = 1000

BASE_URL = "https://avoin-paikkatieto.maanmittauslaitos.fi/kiinteisto-avoin/simple-features/v3"
COLLECTION = "PalstanSijaintitiedot"


def wgs84_to_3067_bbox_str(wgs84_bbox: list[float]) -> str:
    """Convert [min_lat, min_lon, max_lat, max_lon] to EPSG:3067 bbox coords."""
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    minx, miny = transformer.transform(wgs84_bbox[1], wgs84_bbox[0])
    maxx, maxy = transformer.transform(wgs84_bbox[3], wgs84_bbox[2])
    return f"{minx:.1f},{miny:.1f},{maxx:.1f},{maxy:.1f}"


def fetch_all_parcels(bbox_3067: str) -> list[dict]:
    """Fetch all parcel features from MML with pagination via next-link."""
    all_features = []
    crs_param = "http://www.opengis.net/def/crs/EPSG/0/3067"

    url = (
        f"{BASE_URL}/collections/{COLLECTION}/items"
        f"?bbox={bbox_3067}"
        f"&bbox-crs={crs_param}"
        f"&crs={crs_param}"
        f"&limit={PAGE_LIMIT}"
    )

    page = 0
    while url:
        page += 1
        resp = requests.get(url, auth=(MML_KEY or "", ""), timeout=120)  # MML_KEY checked above
        if resp.status_code == 401:
            print("  ERROR: MML API key rejected. Set MML_KEY env var.")
            sys.exit(1)
        if resp.status_code != 200:
            print(f"  MML error {resp.status_code} on page {page}: {resp.text[:200]}")
            break

        data = resp.json()
        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        print(f"  Page {page}: {len(features)} features (total: {len(all_features)})")

        # Follow next link
        url = None
        for link in data.get("links", []):
            if link.get("rel") == "next":
                url = link["href"]
                break
        time.sleep(0.3)

    return all_features


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not MML_KEY:
        print(
            "ERROR: MML_KEY not found.\n"
            "  Add it to config/keys.json or set the MML_KEY env var.\n"
            "  Get a free key at https://omatili.maanmittauslaitos.fi\n"
            '  Example: echo \'{"MML_KEY": "your-key"}\' > config/keys.json'
        )
        sys.exit(1)

    bbox_3067 = wgs84_to_3067_bbox_str(AOI_BBOX_WGS84)
    area_km2 = (
        float(bbox_3067.split(",")[2]) - float(bbox_3067.split(",")[0])
    ) * (
        float(bbox_3067.split(",")[3]) - float(bbox_3067.split(",")[1])
    ) / 1e6

    print(f"Fetching land parcels for AOI (~{area_km2:.0f} km²)...")
    print(f"  This may take a while — parcels at this scale are large.")

    features = fetch_all_parcels(bbox_3067)

    if not features:
        print("  No parcels found.")
        sys.exit(0)

    fc = {"type": "FeatureCollection", "features": features}
    gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:3067")

    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_land_parcels.geojson"
    gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    print(f"\n  Parcels:  {len(gdf)}")
    print(f"  CRS:      EPSG:3067 (native via explicit request)")
    print(f"  Saved:    {out_path.name}")
    print(f"  File:     {out_path}")


if __name__ == "__main__":
    main()

"""
Fetch Finland national boundary from Natural Earth (10m resolution).

Source: Natural Earth vector data (no auth, no API key)
Output: data/etl/finland_boundary.geojson (EPSG:3067)
"""

import sys
from pathlib import Path

import geopandas as gpd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

ETL_DIR = ROOT / "data" / "etl"
TARGET_CRS = "EPSG:3067"
NE_URL = "https://github.com/nvkelso/natural-earth-vector/raw/master/geojson/ne_10m_admin_0_countries.geojson"


def main():
    ETL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ETL_DIR / "finland_boundary.geojson"

    if out_path.exists():
        print(f"  Finland boundary already exists — skipping fetch")
        return

    world_path = ETL_DIR / "ne_10m_admin_0_countries.geojson"

    print("Downloading Natural Earth countries (13 MB)...")
    r = requests.get(NE_URL, timeout=60)
    r.raise_for_status()
    world_path.write_bytes(r.content)

    print("Extracting Finland...")
    gdf = gpd.read_file(world_path)
    fin = gdf[gdf["ISO_A3"] == "FIN"].copy()
    fin = fin.set_crs("EPSG:4326")
    fin = fin.to_crs(TARGET_CRS)
    fin.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    area_km2 = fin.geometry.area.iloc[0] / 1e6
    print(f"  Area:  {area_km2:,.0f} km²")
    print(f"  CRS:   {TARGET_CRS}")
    print(f"  Saved: {out_path.name}")

    # Cleanup
    world_path.unlink()


if __name__ == "__main__":
    main()

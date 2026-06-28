"""
Download Finland national boundary from Natural Earth.
"""

import sys
from pathlib import Path
import geopandas as gpd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

ETL_DIR = ROOT / "data" / "etl"
URL = "https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/cultural/ne_10m_admin_0_countries.zip"


def main():
    ETL_DIR.mkdir(parents=True, exist_ok=True)
    out = ETL_DIR / "finland_boundary.geojson"

    print(f"Downloading Natural Earth countries (100m)...")
    world = gpd.read_file(URL)
    finland = world[world["NAME"].str.lower() == "finland"]
    if finland.empty:
        print("ERROR: Finland not found in dataset")
        sys.exit(1)

    finland = finland.to_crs("EPSG:3067")
    area_km2 = finland.geometry.area.iloc[0] / 1e6
    finland = finland.to_crs("EPSG:4326")
    finland.to_file(out, driver="GeoJSON", encoding="utf-8")
    print(f"  Area: {area_km2:,.0f} km²")
    print(f"  Saved: {out.name}")


if __name__ == "__main__":
    main()

"""
Download Finland boundary from Natural Earth.
"""

import sys, tempfile, zipfile, io
from pathlib import Path

import geopandas as gpd
import requests

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

ETL_DIR = ROOT / "data" / "etl"
URL = "https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/cultural/ne_10m_admin_0_countries.zip"


def main():
    ETL_DIR.mkdir(parents=True, exist_ok=True)
    out = ETL_DIR / "finland_boundary.geojson"

    print("Downloading Natural Earth countries...")
    r = requests.get(URL, headers={"User-Agent": "GIS-Script/1.0"}, timeout=120)
    r.raise_for_status()

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(tmp)
        world = gpd.read_file(Path(tmp) / "ne_10m_admin_0_countries.shp")

    finland = world[world["NAME"].str.lower() == "finland"]
    if finland.empty:
        print("ERROR: Finland not found")
        sys.exit(1)

    finland = finland.to_crs("EPSG:3067")
    area = finland.geometry.area.iloc[0] / 1e6
    finland = finland.to_crs("EPSG:4326")
    finland.to_file(out, driver="GeoJSON", encoding="utf-8")
    print(f"  Area: {area:,.0f} km²")
    print(f"  Saved: {out.name}")


if __name__ == "__main__":
    main()

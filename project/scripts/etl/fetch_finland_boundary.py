"""Download Finland boundary from OSM (relation 54224)."""

import sys, json
from pathlib import Path

import geopandas as gpd
import requests

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

ETL_DIR = ROOT / "data" / "etl"
FINLAND_OSM_RELATION = 54224
# polygons.openstreetmap.fr serves OSM relations as GeoJSON
OSM_URL = f"https://polygons.openstreetmap.fr/get_geojson.py?id={FINLAND_OSM_RELATION}&params=0"


def main():
    ETL_DIR.mkdir(parents=True, exist_ok=True)
    out = ETL_DIR / "finland_boundary.geojson"

    print("Downloading Finland boundary from OSM...")
    r = requests.get(OSM_URL, timeout=60)
    if r.status_code != 200:
        print(f"ERROR: OSM polygon API returned {r.status_code}")
        sys.exit(1)

    data = r.json()

    # API returns a raw geometry object (MultiPolygon), not a FeatureCollection
    geom_type = data.get("type", "")
    if geom_type in ("Polygon", "MultiPolygon"):
        gdf = gpd.GeoDataFrame.from_features(
            [{"type": "Feature", "geometry": data, "properties": {"name": "Finland"}}],
            crs="EPSG:4326",
        )
    elif geom_type == "FeatureCollection":
        features = data.get("features", [])
        if not features:
            print("ERROR: Empty FeatureCollection from OSM")
            sys.exit(1)
        gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    else:
        print(f"ERROR: Unexpected OSM response type: {geom_type}")
        sys.exit(1)
    # Keep only the main Finland polygon
    finland = gdf if len(gdf) == 1 else gdf[gdf["name"].str.lower().str.contains("finland", na=False)]
    if finland.empty:
        finland = gdf.iloc[[0]]  # fallback: first feature

    finland = finland.to_crs("EPSG:3067")
    area = finland.geometry.area.iloc[0] / 1e6
    finland = finland.to_crs("EPSG:4326")
    finland.to_file(out, driver="GeoJSON", encoding="utf-8")
    print(f"  Area: {area:,.0f} km²")
    print(f"  Saved: {out.name}")


if __name__ == "__main__":
    main()

"""
Merge exclusion zones into one layer with exclusion_type field.
Each type is DISSOLVED into one multipolygon before merging.
"""

import sys
from pathlib import Path

import geopandas as gpd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

CLIP_DIR = ROOT / "data" / "etl" / "clipped"
EXCL_DIR = ROOT / "data" / "etl" / "exclusions"
TARGET_CRS = "EPSG:3067"

LAYERS = [
    ("natura2000", "natura2000"),
    ("flood_river_100a", "flood_river_100a"),
    ("flood_river_250a", "flood_river_250a"),
    ("flood_sea_100a", "flood_sea_100a"),
    ("flood_sea_50a", "flood_sea_50a"),
    ("reserves_state", "nature_reserve_state"),
    ("reserves_private", "nature_reserve_private"),
    ("reserves_spa", "nature_reserve_spa"),
    ("reserves_sac", "nature_reserve_sac"),
]


def find(pattern: str) -> Path | None:
    for f in sorted(CLIP_DIR.iterdir()):
        if pattern in f.name and f.suffix == ".geojson":
            return f
    return None


def main():
    EXCL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXCL_DIR / f"{AOI_CITY}_FINLAND_exclusion_zones.geojson"
    dissolved = []

    for pattern, excl_type in LAYERS:
        fpath = find(pattern)
        if fpath is None:
            print(f"  SKIP: no '{pattern}'")
            continue
        try:
            gdf = gpd.read_file(fpath)
        except Exception as e:
            print(f"  SKIP: {fpath.name} — {e}")
            continue
        if gdf.empty:
            print(f"  SKIP: {fpath.name} empty")
            continue

        if gdf.crs is None:
            gdf.set_crs(TARGET_CRS, inplace=True)
        elif gdf.crs.to_string() != TARGET_CRS:
            gdf = gdf.to_crs(TARGET_CRS)

        before = len(gdf)
        gdf["exclusion_type"] = excl_type
        gdf["_source_file"] = fpath.name
        d = gdf.dissolve(by="exclusion_type", aggfunc="first").reset_index()
        dissolved.append(d)
        print(f"  {excl_type}: {before} → {len(d)} feature(s)")

    if not dissolved:
        print("  No exclusion layers found.")
        sys.exit(0)

    merged = gpd.pd.concat(dissolved, ignore_index=True)

    # Dissolve everything into one — no overlapping polygons
    merged = merged.dissolve().reset_index(drop=True)
    merged["exclusion_type"] = "exclusion_zone"
    merged["_source_file"] = "merged"

    # Area in projected CRS before reprojecting to 4326
    area_km2 = merged.geometry.area.iloc[0] / 1e6 if not merged.empty else 0.0

    merged = merged.to_crs("EPSG:4326")
    merged.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    print(f"\n  Merged: 1 feature (all zones dissolved)")
    print(f"  Area:   {area_km2:,.0f} km²")
    print(f"  Saved:  {out_path.name}")


if __name__ == "__main__":
    main()

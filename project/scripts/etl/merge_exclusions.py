"""
Merge all exclusion zones into a single layer with exclusion_type field.
Each exclusion type is DISSOLVED into one multipolygon before merging.

Inputs:  Natura2000, flood zones (4 layers), nature reserves (4 layers)
Output:  data/etl/exclusions/{CITY}_FINLAND_exclusion_zones.geojson (EPSG:3067)
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

EXCLUSION_LAYERS = [
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


def find_layer(pattern: str) -> Path | None:
    """Find a clipped file matching pattern."""
    for f in sorted(CLIP_DIR.iterdir()):
        if pattern in f.name and f.suffix == ".geojson":
            return f
    # Fallback to raw
    for f in sorted(Path(__file__).resolve().parent.parent.parent.glob("data/raw/*.geojson")):
        if pattern in f.name:
            return f
    return None


def main():
    EXCL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXCL_DIR / f"{AOI_CITY}_FINLAND_exclusion_zones.geojson"

    dissolved = []

    for pattern, excl_type in EXCLUSION_LAYERS:
        fpath = find_layer(pattern)
        if fpath is None:
            print(f"  SKIP: no file matching '{pattern}'")
            continue

        try:
            gdf = gpd.read_file(fpath)
        except Exception as e:
            print(f"  SKIP: {fpath.name} — {e}")
            continue

        if gdf.empty:
            print(f"  SKIP: {fpath.name} (empty)")
            continue

        # Ensure CRS
        if gdf.crs is None:
            gdf.set_crs(TARGET_CRS, inplace=True)
        elif gdf.crs.to_string() != TARGET_CRS:
            gdf = gdf.to_crs(TARGET_CRS)

        before = len(gdf)

        # Dissolve all features of this type into one multipolygon
        gdf["exclusion_type"] = excl_type
        gdf["_source_file"] = fpath.name
        dissolved_gdf = gdf.dissolve(by="exclusion_type", aggfunc="first").reset_index()

        dissolved.append(dissolved_gdf)
        after = len(dissolved_gdf)
        print(f"  {excl_type}: {before} → {after} feature(s) (dissolved)")

    if not dissolved:
        print("  No exclusion layers found.")
        sys.exit(0)

    merged = gpd.pd.concat(dissolved, ignore_index=True)
    # GeoJSON spec requires WGS84
    merged = merged.to_crs("EPSG:4326")

    merged.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    print(f"\n  Merged exclusion zones: {len(merged)} total features")
    for typ in merged["exclusion_type"]:
        print(f"    {typ}")
    print(f"  Saved: {out_path.name}")


if __name__ == "__main__":
    main()

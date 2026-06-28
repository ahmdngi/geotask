"""
Merge all exclusion zones into a single layer with exclusion_type field.

Inputs:  Natura2000, flood zones (4 layers), nature reserves (4 layers)
Output:  data/etl/exclusions/{CITY}_FINLAND_exclusion_zones.geojson (EPSG:3067)

Each feature gets an `exclusion_type` field identifying its category.
No filtering — all overlapping zones are preserved.
"""

import sys
from pathlib import Path

import geopandas as gpd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

RAW_DIR = ROOT / "data" / "raw"
EXCL_DIR = ROOT / "data" / "etl" / "exclusions"
TARGET_CRS = "EPSG:3067"

EXCLUSION_LAYERS = [
    # (filename_contains, exclusion_type)
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
    """Find a raw data file matching pattern."""
    for f in RAW_DIR.iterdir():
        if pattern in f.name and f.suffix == ".geojson":
            return f
    return None


def main():
    EXCL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXCL_DIR / f"{AOI_CITY}_FINLAND_exclusion_zones.geojson"

    all_gdfs = []
    found = 0

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

        gdf["exclusion_type"] = excl_type
        # Keep only essential fields + original attributes
        gdf["_source_file"] = fpath.name
        all_gdfs.append(gdf)
        found += 1
        print(f"  {excl_type}: {len(gdf)} features ({fpath.name})")

    if not all_gdfs:
        print("  No exclusion layers found. Run fetch scripts first.")
        sys.exit(0)

    merged = gpd.pd.concat(all_gdfs, ignore_index=True)

    # Simplify: keep id/name if they exist, + exclusion_type + _source_file
    keep_cols = ["exclusion_type", "_source_file"]
    for col in ["id", "name", "natura_layer", "sitecode", "sitename"]:
        if col in merged.columns:
            keep_cols.append(col)

    cols_to_drop = [c for c in merged.columns if c not in keep_cols and c != "geometry"]
    if cols_to_drop:
        merged.drop(columns=cols_to_drop, inplace=True)

    merged.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    counts = merged["exclusion_type"].value_counts()
    print(f"\n  Merged exclusion zones: {len(merged)} total features")
    for typ, cnt in counts.items():
        print(f"    {typ}: {cnt}")
    print(f"  Saved: {out_path.name}")


if __name__ == "__main__":
    main()

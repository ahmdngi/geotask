"""
Clip all raw data to AOI circular buffer + Finland boundary.
Inputs:  data/raw/*.geojson/tiff, data/etl/finland_boundary.geojson
Outputs: data/etl/clipped/
"""

import sys
from pathlib import Path

import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask
from shapely.ops import transform

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY, AOI_BUFFER_POLY

RAW_DIR = ROOT / "data" / "raw"
ETL_DIR = ROOT / "data" / "etl"
CLIP_DIR = ETL_DIR / "clipped"
TARGET_CRS = "EPSG:3067"
SKIP_FILES = {"finland_boundary.geojson"}


def load_boundary() -> gpd.GeoDataFrame | None:
    p = ETL_DIR / "finland_boundary.geojson"
    if not p.exists():
        return None
    b = gpd.read_file(p)
    if b.crs is None or b.crs.to_string() != TARGET_CRS:
        b = b.to_crs(TARGET_CRS)
    return b


def clean(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    before = len(gdf)
    gdf = gdf[gdf.geometry.notna()]
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
        gdf = gdf[gdf.geometry.is_valid]
    if len(gdf) != before:
        print(f"(cleaned: {before - len(gdf)} removed)", end=" ")
    return gdf


def main():
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    aoi_3067 = transform(t.transform, AOI_BUFFER_POLY)
    aoi_mask = gpd.GeoDataFrame(geometry=[aoi_3067], crs=TARGET_CRS)

    boundary = load_boundary()
    if boundary is not None:
        print(f"  Finland: {boundary.geometry.area.iloc[0] / 1e6:,.0f} km²")

    for fpath in sorted(RAW_DIR.iterdir()):
        if fpath.name in SKIP_FILES:
            continue
        out = CLIP_DIR / fpath.name

        if fpath.suffix == ".tiff":
            if boundary is None:
                print(f"  SKIP {fpath.name} (no boundary)")
                continue
            print(f"  {fpath.name}...", end=" ", flush=True)
            try:
                intersect = gpd.overlay(aoi_mask, boundary, how="intersection")
                from shapely.geometry import mapping
                with rasterio.open(fpath) as src:
                    img, xf = rio_mask(src, [mapping(intersect.geometry.union_all())], crop=True, filled=False)
                    meta = src.meta.copy()
                    meta.update({"height": img.shape[1], "width": img.shape[2], "transform": xf})
                    with rasterio.open(out, "w", **meta) as dst:
                        dst.write(img)
                print("clipped")
            except Exception as e:
                print(f"ERROR: {e}")

        elif fpath.suffix == ".geojson":
            print(f"  {fpath.name}...", end=" ", flush=True)
            try:
                gdf = gpd.read_file(fpath)
                if gdf.empty:
                    print("empty")
                    continue

                # Fix invalid geometries BEFORE clipping
                if gdf.crs is None:
                    # Auto-detect CRS from coordinate range
                    bounds = gdf.geometry.total_bounds  # [minx, miny, maxx, maxy]
                    if bounds[0] > -180 and bounds[2] < 180 and bounds[1] > -90 and bounds[3] < 90:
                        gdf.set_crs("EPSG:4326", inplace=True)
                        gdf = gdf.to_crs(TARGET_CRS)
                    else:
                        gdf.set_crs(TARGET_CRS, inplace=True)
                elif gdf.crs.to_string() != TARGET_CRS:
                    gdf = gdf.to_crs(TARGET_CRS)

                invalid = ~gdf.geometry.is_valid
                if invalid.any():
                    gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
                    gdf = gdf[gdf.geometry.is_valid]
                    if gdf.empty:
                        print("empty (all invalid)")
                        continue

                gdf = gpd.clip(gdf, aoi_mask)
                if boundary is not None and not gdf.empty:
                    gdf = gpd.clip(gdf, boundary)

                gdf = clean(gdf)
                if gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).any():
                    gdf.geometry = gdf.geometry.simplify(2.0)
                gdf = gdf.to_crs("EPSG:4326")
                gdf.to_file(out, driver="GeoJSON", encoding="utf-8")
                print(f"{len(gdf)} features")
            except Exception as e:
                print(f"ERROR: {e}")

    print(f"\nDone: {CLIP_DIR}")


if __name__ == "__main__":
    main()

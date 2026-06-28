"""
Clip all raw data layers to AOI + Finland national boundary.

Inputs:  data/raw/*.geojson, data/raw/*.tiff, data/etl/finland_boundary.geojson
Outputs: data/etl/clipped/{LAYER}.geojson / .tiff

If a Finland boundary exists, all outputs are clipped to it (prevents
Helsinki bbox from including Tallinn / Estonia).
"""

import sys
from pathlib import Path

import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask
from shapely.geometry import box, mapping
from shapely.ops import transform

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY, AOI_BUFFER_POLY

RAW_DIR = ROOT / "data" / "raw"
ETL_DIR = ROOT / "data" / "etl"
CLIP_DIR = ETL_DIR / "clipped"
TARGET_CRS = "EPSG:3067"

# Files to skip in clipping
SKIP_FILES = {"finland_boundary.geojson"}


def load_finland_boundary() -> gpd.GeoDataFrame | None:
    bpath = ETL_DIR / "finland_boundary.geojson"
    if bpath.exists():
        return gpd.read_file(bpath)
    return None


def clean_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop null geometries and fix invalid self-intersections."""
    before = len(gdf)

    # Drop null geometries
    gdf = gdf[gdf.geometry.notna()]

    # Fix invalid geometries with zero-width buffer
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
        # Drop any that are still invalid after fix
        still_invalid = ~gdf.geometry.is_valid
        if still_invalid.any():
            print(f"      (dropped {still_invalid.sum()} unfixable geometries)", end=" ")
            gdf = gdf[gdf.geometry.is_valid]

    after = len(gdf)
    if before != after:
        print(f"(cleaned: {before - after} removed)", end=" ")
    return gdf


def clip_vector(gdf: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clip a vector layer to the Finland boundary."""
    if gdf.crs is None:
        gdf.set_crs(TARGET_CRS, inplace=True)
    if gdf.crs.to_string() != TARGET_CRS:
        gdf = gdf.to_crs(TARGET_CRS)
    clipped = gpd.clip(gdf, boundary)
    return clipped


def clip_raster(tif_path: Path, boundary: gpd.GeoDataFrame, out_path: Path):
    """Clip a raster to the Finland boundary."""
    with rasterio.open(tif_path) as src:
        geoms = [mapping(boundary.geometry.union_all())]
        out_image, out_transform = rio_mask(src, geoms, crop=True, filled=False)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
        })
        with rasterio.open(out_path, "w", **out_meta) as dst:
            dst.write(out_image)


def main():
    CLIP_DIR.mkdir(parents=True, exist_ok=True)

    # Build AOI circular buffer in EPSG:3067
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    aoi_buffer_3067 = transform(transformer.transform, AOI_BUFFER_POLY)
    aoi_mask = gpd.GeoDataFrame(geometry=[aoi_buffer_3067], crs=TARGET_CRS)

    # Load Finland boundary mask
    boundary = load_finland_boundary()
    if boundary is not None:
        print(f"  Finland boundary loaded: {boundary.geometry.area.iloc[0] / 1e6:,.0f} km²")
    else:
        print(f"  WARNING: No Finland boundary found — skipping national mask")
        print(f"  Run fetch_finland_boundary.py first for better results")

    files = list(RAW_DIR.iterdir())
    print(f"\nClipping {len(files)} files to AOI + Finland boundary...\n")

    for fpath in sorted(files):
        if fpath.name in SKIP_FILES:
            continue

        out_path = CLIP_DIR / fpath.name

        if fpath.suffix == ".tiff":
            if boundary is None:
                print(f"  SKIP raster: {fpath.name} (no boundary to clip)")
                continue
            print(f"  {fpath.name}...", end=" ", flush=True)
            try:
                # Clip raster to buffer ∩ boundary
                from shapely.geometry import mapping as rio_mapping
                intersect = gpd.overlay(aoi_mask, boundary, how="intersection")
                clip_geom = [rio_mapping(intersect.geometry.union_all())]
                with rasterio.open(fpath) as src:
                    out_image, out_transform = rio_mask(src, clip_geom, crop=True, filled=False)
                    out_meta = src.meta.copy()
                    out_meta.update({
                        "driver": "GTiff",
                        "height": out_image.shape[1],
                        "width": out_image.shape[2],
                        "transform": out_transform,
                    })
                    with rasterio.open(out_path, "w", **out_meta) as dst:
                        dst.write(out_image)
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
                # Ensure CRS
                if gdf.crs is None:
                    gdf.set_crs(TARGET_CRS, inplace=True)
                elif gdf.crs.to_string() != TARGET_CRS:
                    gdf = gdf.to_crs(TARGET_CRS)

                # Clip to AOI bbox first
                gdf = clip_vector(gdf, aoi_mask)

                # Then clip to Finland boundary if available
                if boundary is not None and not gdf.empty:
                    gdf = clip_vector(gdf, boundary)

                # Clean geometries before saving
                gdf = clean_geometries(gdf)

                # Simplify polygon geometries for web-friendly output
                if gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).any():
                    gdf.geometry = gdf.geometry.simplify(5.0)

                # GeoJSON spec requires WGS84 — auto-reproject
                gdf = gdf.to_crs("EPSG:4326")

                gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")
                print(f"{len(gdf)} features")
            except Exception as e:
                print(f"ERROR: {e}")

    print(f"\nDone. Clipped files in: {CLIP_DIR}")


if __name__ == "__main__":
    main()

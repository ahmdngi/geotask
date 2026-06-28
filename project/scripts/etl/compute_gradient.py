"""
Compute gradient (slope) from DEM, reclassify to <8% suitable, vectorize.

Uses same approach as Chunk 3d in notebook:
  - scipy.ndimage.sobel for slope computation
  - rasterio for DEM I/O
  - slope in percent, threshold < 8%

Input:  data/raw/{CITY}_FINLAND_mml_dem_2m.tiff
Output: data/etl/suitability/{CITY}_FINLAND_gradient_lt8.geojson (EPSG:3067)
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features as rio_features
from scipy.ndimage import sobel
from shapely.geometry import shape

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

RAW_DIR = ROOT / "data" / "raw"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
TARGET_CRS = "EPSG:3067"


def main():
    SUIT_DIR.mkdir(parents=True, exist_ok=True)

    dem_path = RAW_DIR / f"{AOI_CITY}_FINLAND_mml_dem_2m.tiff"
    slope_tif = SUIT_DIR / f"{AOI_CITY}_FINLAND_slope_percent.tiff"
    suitable_tif = SUIT_DIR / f"{AOI_CITY}_FINLAND_gradient_suitable_8pct.tiff"
    out_vector = SUIT_DIR / f"{AOI_CITY}_FINLAND_gradient_lt8.geojson"

    if not dem_path.exists():
        print(f"  ERROR: DEM not found at {dem_path}")
        print(f"  Run fetch_dem.py first")
        sys.exit(1)

    print(f"DEM: {dem_path.name}")

    # === Step 1: Compute slope percent using Sobel (notebook Chunk 3d) ===
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float64)
        profile = src.profile.copy()
        res = src.res
        crs = src.crs
        transform = src.transform

    dx = sobel(dem, axis=1) / res[0]
    dy = sobel(dem, axis=0) / res[1]
    slope_deg = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)
    slope_pct = np.tan(np.deg2rad(slope_deg)) * 100
    slope_pct = np.where(np.isfinite(slope_pct), slope_pct, 10000.0)

    print(f"  Slope range: {slope_pct.min():.1f}% – {slope_pct.max():.1f}%")

    # Save slope raster
    with rasterio.open(
        slope_tif, "w", driver="GTiff",
        height=slope_pct.shape[0], width=slope_pct.shape[1],
        count=1, dtype=np.float32,
        crs=crs, transform=transform,
    ) as dst:
        dst.write(slope_pct.astype(np.float32), 1)
    print(f"  Slope raster: {slope_tif.name}")

    # === Step 2: Reclassify to binary (slope < 8%) ===
    suitable = (slope_pct < 8.0).astype(np.uint8)
    with rasterio.open(
        suitable_tif, "w", driver="GTiff",
        height=suitable.shape[0], width=suitable.shape[1],
        count=1, dtype=np.uint8,
        crs=crs, transform=transform,
        nodata=0,
    ) as dst:
        dst.write(suitable, 1)
    print(f"  Suitable mask: {suitable_tif.name}")

    # === Step 3: Vectorize suitable areas ===
    results = rio_features.shapes(
        suitable,
        transform=transform,
        mask=suitable == 1,
    )

    features = []
    for geom_val, val in results:
        if val != 1:
            continue
        features.append({
            "type": "Feature",
            "geometry": shape(geom_val),
            "properties": {"suitable": "yes", "gradient_pct": "<8"},
        })

    if not features:
        print("  No areas <8% slope found")
        return

    gdf = gpd.GeoDataFrame.from_features(
        {"type": "FeatureCollection", "features": features}, crs=TARGET_CRS
    )

    # Clean invalid or empty geometries before saving
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty]
    if gdf.empty:
        print("  No valid geometries after cleaning")
        return
    gdf.geometry = gdf.geometry.simplify(10.0)

    # Drop tiny polygons (< 100 m²)
    before = len(gdf)
    gdf = gdf[gdf.geometry.area >= 100]
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty]
    if before != len(gdf):
        print(f"  Removed {before - len(gdf)} tiny polygons")
    gdf.to_file(out_vector, driver="GeoJSON", encoding="utf-8")

    area_km2 = gdf.geometry.area.sum() / 1e6
    total_px = suitable.size
    suitable_px = suitable.sum()
    pct = suitable_px / total_px * 100
    print(f"  Suitable area: {area_km2:.1f} km² ({pct:.1f}% of DEM)")
    print(f"  Vector:        {out_vector.name}")


if __name__ == "__main__":
    main()

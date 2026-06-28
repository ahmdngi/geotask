"""Compute slope gradient from DEM, create binary mask (<8% suitable).
Outputs:
  - slope_percent.tiff          (float32)
  - gradient_suitable_8pct.tiff (uint8 binary mask: 1 = suitable)
"""

import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import sobel

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

DATA_DIR = ROOT / "data" / "etl"
CLIP_DIR = DATA_DIR / "clipped"
SUIT_DIR = DATA_DIR / "suitability"
TARGET_CRS = "EPSG:3067"


def main():
    SUIT_DIR.mkdir(parents=True, exist_ok=True)

    dem_path = next((f for f in sorted(CLIP_DIR.iterdir()) if "dem" in f.name and f.suffix == ".tiff"), None)
    if dem_path is None:
        print("No DEM file found in clipped data.")
        sys.exit(0)

    prefix = f"{AOI_CITY}_FINLAND"
    slope_tif = SUIT_DIR / f"{prefix}_slope_percent.tiff"
    mask_tif = SUIT_DIR / f"{prefix}_gradient_suitable_8pct.tiff"

    print(f"DEM: {dem_path.name}")

    # Read DEM and compute slope
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float64)
        crs = src.crs
        transform = src.transform

    dx = sobel(dem, axis=1) / 30.0
    dy = sobel(dem, axis=0) / 30.0
    slope_deg = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)
    slope_pct = np.tan(np.deg2rad(slope_deg)) * 100
    slope_pct = np.where(np.isfinite(slope_pct), slope_pct, 10000.0)

    # Write slope raster
    with rasterio.open(slope_tif, "w", driver="GTiff",
                       height=slope_pct.shape[0], width=slope_pct.shape[1],
                       count=1, dtype=np.float32, crs=crs, transform=transform) as dst:
        dst.write(slope_pct.astype(np.float32), 1)
    print(f"  Slope:     {slope_tif.name}")

    # Binary mask: 1 = slope < 8%
    suitable = (slope_pct < 8.0).astype(np.uint8)
    with rasterio.open(mask_tif, "w", driver="GTiff",
                       height=suitable.shape[0], width=suitable.shape[1],
                       count=1, dtype=np.uint8, crs=crs, transform=transform,
                       nodata=0, tiled=True, blockxsize=256, blockysize=256,
                       compress="lzw", interleave="band") as dst:
        dst.write(suitable, 1)
        dst.build_overviews([2, 4, 8, 16], rasterio.enums.Resampling.nearest)
        dst.update_tags(ns='rio_overview', resampling='nearest')
    print(f"  Mask:      {mask_tif.name}")

    total_px = suitable.size
    suitable_px = suitable.sum()
    pct = suitable_px / total_px * 100
    area_km2 = suitable_px * (abs(transform[0]) * abs(transform[4])) / 1e6
    print(f"  Suitable:  {area_km2:.1f} km² ({pct:.1f}% of DEM)")


if __name__ == "__main__":
    main()

"""
Compute slope gradient from DEM, reclassify <8% suitable areas.
Outputs: TIFF rasters + vectorized GeoJSON of suitable areas.
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

DATA_DIR = ROOT / "data" / "etl"
CLIP_DIR = DATA_DIR / "clipped"
SUIT_DIR = DATA_DIR / "suitability"
TARGET_CRS = "EPSG:3067"


def main():
    SUIT_DIR.mkdir(parents=True, exist_ok=True)

    # Find DEM file
    dem_path = next((f for f in sorted(CLIP_DIR.iterdir()) if "dem" in f.name and f.suffix == ".tiff"), None)
    if dem_path is None:
        print("No DEM file found in clipped data.")
        sys.exit(0)

    prefix = f"{AOI_CITY}_FINLAND"
    slope_tif = SUIT_DIR / f"{prefix}_slope_percent.tiff"
    suitable_tif = SUIT_DIR / f"{prefix}_gradient_suitable_8pct.tiff"
    out_vector = SUIT_DIR / f"{prefix}_gradient_lt8.geojson"

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
    print(f"  Slope: {slope_tif.name}")

    # Reclassify <8%
    suitable = (slope_pct < 8.0).astype(np.uint8)
    with rasterio.open(suitable_tif, "w", driver="GTiff",
                       height=suitable.shape[0], width=suitable.shape[1],
                       count=1, dtype=np.uint8, crs=crs, transform=transform, nodata=0) as dst:
        dst.write(suitable, 1)
    print(f"  Suitable mask: {suitable_tif.name}")

    # Vectorize
    results = rio_features.shapes(suitable, transform=transform, mask=suitable == 1)
    features = []
    for geom_val, val in results:
        if val != 1:
            continue
        features.append({"type": "Feature", "geometry": shape(geom_val),
                         "properties": {"suitable": "yes", "gradient_pct": "<8"}})

    if not features:
        print("  No areas <8% slope found")
        return

    gdf = gpd.GeoDataFrame.from_features({"type": "FeatureCollection", "features": features}, crs=TARGET_CRS)
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty]
    if gdf.empty:
        print("  No valid geometries")
        return
    gdf.geometry = gdf.geometry.simplify(10.0)

    before = len(gdf)
    gdf = gdf[gdf.geometry.area >= 100]
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty]
    if len(gdf) != before:
        print(f"  Removed {before - len(gdf)} tiny polygons")

    area_km2 = gdf.geometry.area.sum() / 1e6
    gdf = gdf.to_crs("EPSG:4326")
    gdf.to_file(out_vector, driver="GeoJSON", encoding="utf-8")

    total_px = suitable.size
    pct = suitable.sum() / total_px * 100
    print(f"  Suitable: {area_km2:.1f} km² ({pct:.1f}% of DEM)")
    print(f"  Vector:   {out_vector.name}")


if __name__ == "__main__":
    main()

"""Process DEM tiles in parallel: per-tile gradient → binary mask → polygonize → merge/dissolve.
No full-resolution mask mosaic — goes directly to dissolved GeoJSON.

Input:  data/raw/dem_tiles/*.tiff (raw 2m DEM tiles from MML)
Output: data/etl/suitability/{City}_FINLAND_gradient_suitable_8pct.geojson
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes
from scipy.ndimage import sobel

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

TILES_DIR = ROOT / "data" / "raw" / "dem_tiles"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
WORKERS = 10
SIMPLIFY_TOL = 5  # meters in EPSG:3067


def process_tile(tif_path: Path) -> list[dict]:
    """Read one DEM tile → gradient → binary mask → polygonize → return GeoJSON features."""
    label = tif_path.stem
    feats = []
    try:
        with rasterio.open(tif_path) as src:
            full_dem = src.read(1).astype(np.float64)
            transform = src.transform
            crs = src.crs
            full_h, full_w = full_dem.shape

        # Downsample 8× for fast polygonization
        from scipy.ndimage import zoom
        scale = 1/8
        dem = zoom(full_dem, scale)
        # Adjust transform for downsampled raster
        transform_lo = transform * transform.scale(full_w / dem.shape[1], full_h / dem.shape[0])

        dx = sobel(dem, axis=1) / 30.0
        dy = sobel(dem, axis=0) / 30.0
        slope_deg = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)
        slope_pct = np.tan(np.deg2rad(slope_deg)) * 100
        slope_pct = np.where(np.isfinite(slope_pct), slope_pct, 10000.0)
        mask = (slope_pct < 8.0).astype(np.uint8)

        # Only polygonize if there are suitable pixels
        if mask.sum() == 0:
            return []

        from shapely.geometry import shape, mapping
        for geom, val in shapes(mask, mask=mask, transform=transform_lo):
            if val == 1:
                poly = shape(geom).simplify(SIMPLIFY_TOL)
                feats.append({"type": "Feature", "geometry": mapping(poly), "properties": {}})

        return feats

    except Exception as e:
        print(f"  FAIL {label}: {e}")
        return []


def main():
    if not TILES_DIR.exists():
        print(f"Tile directory not found: {TILES_DIR}\n  Run fetch_dem.py first.")
        sys.exit(0)

    SUIT_DIR.mkdir(parents=True, exist_ok=True)
    tif_paths = sorted(TILES_DIR.glob("*.tiff"))
    tif_paths = [p for p in tif_paths if not p.name.endswith(".mask.tiff")]

    if not tif_paths:
        print("No DEM tiles found.")
        sys.exit(0)

    print(f"Processing {len(tif_paths)} DEM tiles ({WORKERS} workers)...")

    # Phase 1: per-tile gradient → mask → polygonize (parallel)
    t0 = time.time()
    all_features: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fut_map = {pool.submit(process_tile, p): p for p in tif_paths}
        for fut in as_completed(fut_map):
            done += 1
            fs = fut.result()
            all_features.extend(fs)
            print(f"  [{done}/{len(tif_paths)}] {fut_map[fut].stem}: {len(fs)} polygons")

    t1 = time.time()
    print(f"  Polygonized: {len(all_features)} features from {len(tif_paths)} tiles ({t1-t0:.0f}s)")

    if not all_features:
        print("No suitable areas found in any tile.")
        sys.exit(0)

    # Phase 2: merge + dissolve all features
    print("\nMerging and dissolving...")
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union, transform as shp_transform
    import pyproj
    t2 = time.time()

    merged = unary_union([shape(f["geometry"]) for f in all_features])
    # Dissolve (unary_union already merges overlapping/adjacent), then simplify
    dissolved = merged.simplify(SIMPLIFY_TOL * 2)

    # Reproject from EPSG:3067 → EPSG:4326
    proj = pyproj.Transformer.from_crs("EPSG:3067", "EPSG:4326", always_xy=True).transform
    dissolved_wgs84 = shp_transform(proj, dissolved)

    fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": mapping(dissolved_wgs84), "properties": {}}],
    }
    t3 = time.time()
    print(f"  Merged into 1 multipolygon ({t3-t2:.1f}s)")

    # Save
    out_path = SUIT_DIR / f"{AOI_CITY}_FINLAND_gradient_suitable_8pct.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f)
    kb = out_path.stat().st_size / 1024
    print(f"  Saved: {out_path.name} ({kb:.0f} KB)")

    total = time.time() - t0
    print(f"\nDone in {total:.0f}s")


if __name__ == "__main__":
    main()

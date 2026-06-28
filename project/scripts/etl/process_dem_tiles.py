"""Process DEM tiles in parallel: gradient → binary mask → polygonize → GeoJSON + mask TIFF.
Reads tiles at 1/8 resolution (fast I/O), generates dissolved suitability GeoJSON
and binary suitability mask TIFF (uint8, for future analysis).

Input:  data/raw/dem_tiles/*.tiff (raw 2m DEM tiles from MML)
Output: data/etl/suitability/{City}_FINLAND_gradient_suitable_8pct.geojson
        data/etl/suitability/{City}_FINLAND_gradient_suitable_8pct.tiff  (uint8, nodata=0)
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
SIMPLIFY_TOL = 5


def process_tile(tif_path: Path) -> tuple | None:
    """Read tile at 1/8 res → gradient → mask. Returns (mask_array, transform, crs, polys) or None."""
    label = tif_path.stem
    try:
        with rasterio.open(tif_path) as src:
            scale = 8
            h_lo = src.height // scale
            w_lo = src.width // scale
            dem = src.read(1, out_shape=(1, h_lo, w_lo)).astype(np.float64)
            xf_lo = src.transform * src.transform.scale(src.width / w_lo, src.height / h_lo)
            crs = src.crs

        # Gradient
        dx = sobel(dem, axis=1) / 30.0
        dy = sobel(dem, axis=0) / 30.0
        slope_deg = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)
        slope_pct = np.tan(np.deg2rad(slope_deg)) * 100
        slope_pct = np.where(np.isfinite(slope_pct), slope_pct, 10000.0)
        mask = (slope_pct < 8.0).astype(np.uint8)

        if mask.sum() == 0:
            return None

        # Polygonize for GeoJSON
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union
        polys = []
        for geom, val in shapes(mask, mask=mask, transform=xf_lo):
            if val == 1:
                polys.append(shape(geom).simplify(SIMPLIFY_TOL))
        dissolved = unary_union(polys) if polys else None

        return (mask, xf_lo, crs, dissolved)

    except Exception as e:
        print(f"  FAIL {label}: {e}")
        return None


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
    t0 = time.time()

    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union, transform as shp_transform
    import pyproj
    from rasterio.merge import merge
    poly_geoms = []
    mask_entries = []  # (mask_array, transform, crs)
    done = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fut_map = {pool.submit(process_tile, p): p for p in tif_paths}
        for fut in as_completed(fut_map):
            done += 1
            result = fut.result()
            tile = fut_map[fut].stem
            if result:
                mask_arr, xf_lo, crs, dissolved = result
                poly_geoms.append(dissolved)
                mask_entries.append((mask_arr, xf_lo, crs))

                # Incremental merge every 10 tiles
                if len(poly_geoms) >= 10:
                    merged_poly = unary_union(poly_geoms)
                    poly_geoms = [merged_poly]

            print(f"  [{done}/{len(tif_paths)}] {tile}: {'✅' if result else '⏭️'}", flush=True)

    t1 = time.time()
    print(f"  Gradient computed: {done}/{len(tif_paths)} tiles ({t1-t0:.0f}s)")

    if not poly_geoms:
        print("No suitable areas found.")
        sys.exit(0)

    # Final merge → simplify → reproject → save
    merged = unary_union(poly_geoms).simplify(SIMPLIFY_TOL * 2)
    proj = pyproj.Transformer.from_crs("EPSG:3067", "EPSG:4326", always_xy=True).transform
    merged_wgs84 = shp_transform(proj, merged)

    fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": mapping(merged_wgs84), "properties": {}}],
    }

    geojson_path = SUIT_DIR / f"{AOI_CITY}_FINLAND_gradient_suitable_8pct.geojson"
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(fc, f)
    kb = geojson_path.stat().st_size / 1024
    print(f"  GeoJSON: {geojson_path.name} ({kb:.0f} KB) — for viewing")

    # ── Save binary mask TIFF (for future decisions) ──
    print("\nMosaicing binary mask TIFF...")
    from rasterio.io import MemoryFile
    srcs = []
    for arr, xf, crs in mask_entries:
        prof = {
            "driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1],
            "count": 1, "dtype": np.uint8, "crs": crs, "transform": xf,
            "nodata": 0, "tiled": True, "blockxsize": 256, "blockysize": 256,
            "compress": "lzw",
        }
        mem = MemoryFile()
        with mem.open(**prof) as tmp:
            tmp.write(arr, 1)
        srcs.append(mem.open())

    mosaic, xform = merge(srcs, method="first")
    mask_tif = SUIT_DIR / f"{AOI_CITY}_FINLAND_gradient_suitable_8pct.tiff"
    with rasterio.open(mask_tif, "w", driver="GTiff",
                       height=mosaic.shape[1], width=mosaic.shape[2],
                       count=1, dtype=np.uint8, crs="EPSG:3067", transform=xform,
                       nodata=0, tiled=True, blockxsize=256, blockysize=256,
                       compress="lzw") as dst:
        dst.write(mosaic)

    for s in srcs:
        s.close()

    mb = mask_tif.stat().st_size / 1e6
    print(f"  Mask TIFF: {mask_tif.name} ({mb:.1f} MB) — for analysis")

    total = time.time() - t0
    print(f"\nDone in {total:.0f}s")


if __name__ == "__main__":
    main()

"""Process DEM tiles in parallel: gradient → binary mask → mosaic TIFF.

Input:  data/raw/dem_tiles/*.tiff (raw 2m DEM tiles from MML)
Output: data/etl/suitability/{City}_FINLAND_gradient_suitable_8pct.tiff  (uint8, tiled, LZW)
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from scipy.ndimage import sobel

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

TILES_DIR = ROOT / "data" / "raw" / "dem_tiles"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
WORKERS = 10


def process_tile(tif_path: Path) -> tuple | None:
    """Read tile at 1/8 res → gradient → mask. Returns (mask_array, transform, crs) or None."""
    label = tif_path.stem
    try:
        with rasterio.open(tif_path) as src:
            scale = 8
            h_lo = src.height // scale
            w_lo = src.width // scale
            dem = src.read(1, out_shape=(1, h_lo, w_lo)).astype(np.float64)
            xf_lo = src.transform * src.transform.scale(src.width / w_lo, src.height / h_lo)
            crs = src.crs

        dx = sobel(dem, axis=1) / 30.0
        dy = sobel(dem, axis=0) / 30.0
        slope_deg = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)
        slope_pct = np.tan(np.deg2rad(slope_deg)) * 100
        slope_pct = np.where(np.isfinite(slope_pct), slope_pct, 10000.0)
        mask = (slope_pct < 8.0).astype(np.uint8)

        if mask.sum() == 0:
            return None

        return (mask, xf_lo, crs)

    except Exception as e:
        print(f"  FAIL {label}: {e}")
        return None


def main():
    if not TILES_DIR.exists():
        print(f"Tile directory not found: {TILES_DIR}\n  Run fetch_dem.py first.")
        sys.exit(0)

    SUIT_DIR.mkdir(parents=True, exist_ok=True)
    tif_paths = sorted(TILES_DIR.glob("*.tiff"))

    if not tif_paths:
        print("No DEM tiles found.")
        sys.exit(0)

    print(f"Processing {len(tif_paths)} DEM tiles ({WORKERS} workers)...")
    t0 = time.time()

    srcs = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fut_map = {pool.submit(process_tile, p): p for p in tif_paths}
        for fut in as_completed(fut_map):
            done += 1
            result = fut.result()
            tile = fut_map[fut].stem
            if result:
                mask_arr, xf_lo, crs = result
                prof = {
                    "driver": "GTiff", "height": mask_arr.shape[0], "width": mask_arr.shape[1],
                    "count": 1, "dtype": np.uint8, "crs": crs, "transform": xf_lo,
                    "nodata": 0, "tiled": True, "blockxsize": 256, "blockysize": 256,
                    "compress": "lzw",
                }
                mem = MemoryFile()
                with mem.open(**prof) as tmp:
                    tmp.write(mask_arr, 1)
                srcs.append(mem.open())
            print(f"  [{done}/{len(tif_paths)}] {tile}: {'✅' if result else '⏭️'}", flush=True)

    t1 = time.time()
    print(f"  Masks computed: {len(srcs)}/{len(tif_paths)} tiles ({t1-t0:.0f}s)")

    if not srcs:
        print("No suitable areas found.")
        sys.exit(0)

    # Mosaic all masks
    print("\nMosaicing binary masks...")
    mosaic, xform = merge(srcs, method="first")

    out = SUIT_DIR / f"{AOI_CITY}_FINLAND_gradient_suitable_8pct.tiff"
    with rasterio.open(out, "w", driver="GTiff",
                       height=mosaic.shape[1], width=mosaic.shape[2],
                       count=1, dtype=np.uint8, crs="EPSG:3067", transform=xform,
                       nodata=0, tiled=True, blockxsize=256, blockysize=256,
                       compress="lzw") as dst:
        dst.write(mosaic)

    for s in srcs:
        s.close()

    mb = out.stat().st_size / 1e6
    print(f"  Saved: {out.name} ({mb:.1f} MB)")

    reproject_to_web(out)

    total = time.time() - t0
    print(f"\nDone in {total:.0f}s")


def reproject_to_web(src_path: Path, dst_crs: str = "EPSG:4326") -> Path:
    """Reproject the suitability mask to a web COG for plotting; keep the original."""
    dst_path = src_path.with_name(src_path.stem + "_web.tiff")
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds)
        prof = src.profile.copy()
        prof.update(crs=dst_crs, transform=transform, width=width, height=height,
                    tiled=True, blockxsize=256, blockysize=256, compress="lzw", nodata=0)
        with rasterio.open(dst_path, "w", **prof) as dst:
            reproject(rasterio.band(src, 1), rasterio.band(dst, 1),
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=transform, dst_crs=dst_crs,
                      resampling=Resampling.nearest)
            dst.build_overviews([2, 4, 8, 16], Resampling.nearest)
    print(f"  Saved: {dst_path.name} ({dst_path.stat().st_size / 1e6:.1f} MB, {dst_crs})")
    return dst_path


if __name__ == "__main__":
    main()

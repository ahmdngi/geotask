"""Process DEM tiles to slope + binary mask in parallel, then mosaic masks.
Skips the intermediate full-DEM mosaic — avoids BIGTIFF issues.

Input:  data/raw/dem_tiles/*.tiff (raw 2m DEM tiles from MML)
Output: data/etl/suitability/{City}_FINLAND_gradient_suitable_8pct.tiff
        data/etl/suitability/{City}_FINLAND_slope_percent.tiff
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from scipy.ndimage import sobel

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

TILES_DIR = ROOT / "data" / "raw" / "dem_tiles"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
WORKERS = 10


def process_tile(tif_path: Path) -> tuple[str, Path, Path] | None:
    """Compute slope + binary mask for one tile. Returns (label, mask_path, slope_path) or None."""
    label = tif_path.stem

    try:
        with rasterio.open(tif_path) as src:
            dem = src.read(1).astype(np.float64)
            crs = src.crs
            transform = src.transform
            profile = src.profile.copy()
            height, width = dem.shape

        dx = sobel(dem, axis=1) / 30.0
        dy = sobel(dem, axis=0) / 30.0
        slope_deg = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)
        slope_pct = np.tan(np.deg2rad(slope_deg)) * 100
        slope_pct = np.where(np.isfinite(slope_pct), slope_pct, 10000.0)

        mask = (slope_pct < 8.0).astype(np.uint8)

        # Write mask tile
        mask_path = tif_path.with_suffix(f".mask.tiff")
        with rasterio.open(mask_path, "w", driver="GTiff",
                           height=height, width=width,
                           count=1, dtype=np.uint8, crs=crs, transform=transform,
                           nodata=0, tiled=True, blockxsize=256, blockysize=256,
                           compress="lzw", interleave="band") as dst:
            dst.write(mask, 1)

        # Write slope tile
        slope_path = tif_path.with_suffix(f".slope.tiff")
        with rasterio.open(slope_path, "w", driver="GTiff",
                           height=height, width=width,
                           count=1, dtype=np.float32, crs=crs, transform=transform,
                           tiled=True, blockxsize=256, blockysize=256,
                           compress="lzw", interleave="band") as dst:
            dst.write(slope_pct.astype(np.float32), 1)

        return (label, mask_path, slope_path)

    except Exception as e:
        print(f"  FAIL {label}: {e}")
        return None


def mosaic_tiles(tile_paths: list[Path], out_path: Path, dtype, nodata=None) -> bool:
    """Mosaic a list of single-band TIFFs into one."""
    if not tile_paths:
        return False

    srcs = []
    for p in tile_paths:
        try:
            srcs.append(rasterio.open(p))
        except Exception:
            continue

    if not srcs:
        return False

    mosaic, transform = merge(srcs, method="first")
    profile = srcs[0].profile.copy()
    profile.update({
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": transform,
        "dtype": dtype,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "lzw",
        "BIGTIFF": "YES",
    })
    if nodata is not None:
        profile["nodata"] = nodata

    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(mosaic)

    for src in srcs:
        src.close()

    mb = out_path.stat().st_size / 1e6
    print(f"  Mosaiced: {out_path.name} ({mb:.1f} MB)")
    return True


def main():
    if not TILES_DIR.exists():
        print(f"Tile directory not found: {TILES_DIR}")
        print("  Run fetch_dem.py first.")
        sys.exit(0)

    SUIT_DIR.mkdir(parents=True, exist_ok=True)
    tif_paths = sorted(TILES_DIR.glob("*.tiff"))
    # Filter out previously generated mask/slope tiles
    tif_paths = [p for p in tif_paths if not p.name.endswith((".mask.tiff", ".slope.tiff"))]

    if not tif_paths:
        print("No DEM tiles found.")
        sys.exit(0)

    print(f"Processing {len(tif_paths)} DEM tiles ({WORKERS} workers)...")

    # Phase 1: compute slope + mask for each tile (parallel)
    t0 = time.time()
    mask_paths = []
    slope_paths = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fut_map = {pool.submit(process_tile, p): p for p in tif_paths}
        for fut in as_completed(fut_map):
            done += 1
            result = fut.result()
            if result:
                label, mp, sp = result
                mask_paths.append(mp)
                slope_paths.append(sp)
                print(f"  [{done}/{len(tif_paths)}] {label}: ✅")

    t1 = time.time()
    print(f"  Gradient computed: {len(mask_paths)}/{len(tif_paths)} tiles ({t1-t0:.0f}s)")

    if not mask_paths:
        print("No tiles produced valid masks — aborting.")
        sys.exit(1)

    # Phase 2: mosaic masks
    prefix = f"{AOI_CITY}_FINLAND"
    mask_out = SUIT_DIR / f"{prefix}_gradient_suitable_8pct.tiff"
    print("\nMosaicing binary masks...")
    mosaic_tiles(mask_paths, mask_out, np.uint8, nodata=0)

    # Phase 3: mosaic slope tiles
    slope_out = SUIT_DIR / f"{prefix}_slope_percent.tiff"
    print("\nMosaicing slope tiles...")
    mosaic_tiles(slope_paths, slope_out, np.float32)

    # Cleanup temp mask/slope tiles
    for p in list(TILES_DIR.glob("*.mask.tiff")) + list(TILES_DIR.glob("*.slope.tiff")):
        p.unlink(missing_ok=True)

    total = time.time() - t0
    print(f"\nDone in {total:.0f}s")


if __name__ == "__main__":
    main()

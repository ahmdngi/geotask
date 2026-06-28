"""Mosaic individual DEM tiles into a single contiguous GeoTIFF.
Input:  data/raw/dem_tiles/*.tiff
Output: data/raw/{City}_FINLAND_mml_dem_2m.tiff
"""

import sys
from pathlib import Path

import rasterio
from rasterio.merge import merge

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

TILES_DIR = ROOT / "data" / "raw" / "dem_tiles"
OUT_PATH = ROOT / "data" / "raw" / f"{AOI_CITY}_FINLAND_mml_dem_2m.tiff"


def main():
    if not TILES_DIR.exists():
        print(f"Tile directory not found: {TILES_DIR}")
        print("  Run fetch_dem.py first to generate tiles.")
        sys.exit(0)

    tif_paths = sorted(TILES_DIR.glob("*.tiff"))
    if not tif_paths:
        print(f"No TIFF tiles found in {TILES_DIR}")
        sys.exit(0)

    print(f"Mosaicing {len(tif_paths)} DEM tiles...")
    src_files = []
    for p in tif_paths:
        try:
            src = rasterio.open(p)
            src_files.append(src)
        except Exception as e:
            print(f"  SKIP {p.name}: {e}")

    if not src_files:
        print("No valid tiles to mosaic.")
        sys.exit(0)

    print(f"  Opened {len(src_files)} valid tiles")

    # Merge tiles — use first valid data where they overlap
    mosaic, transform = merge(src_files, method="first")
    profile = src_files[0].profile.copy()
    profile.update({
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": transform,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "lzw",
    })

    with rasterio.open(OUT_PATH, "w", **profile) as dst:
        dst.write(mosaic)

    for src in src_files:
        src.close()

    mb = OUT_PATH.stat().st_size / 1e6
    print(f"  Mosaiced: {OUT_PATH.name} ({mb:.1f} MB)")
    print(f"  Shape:    {mosaic.shape[1]}×{mosaic.shape[2]}")


if __name__ == "__main__":
    main()

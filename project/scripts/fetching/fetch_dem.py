"""Fetch DEM tiles from MML OGC API Processes covering the full AOI buffer.
Splits the AOI bounding box into a grid of tiles and fetches concurrently.
Output: multiple TIFF tiles in data/raw/dem_tiles/
"""

import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_BUFFER_POLY, AOI_CITY, MML_KEY, MML_DEM_PROC

TILE_SIZE_M = 10000      # 10 km × 10 km tiles (~100 km² each) — MML rejects larger
TILES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "dem_tiles"
WORKERS = 10
POLL_INTERVAL = 5
POLL_MAX = 60
PROCESS_ID = "korkeusmalli_2m_bbox"


def wgs84_to_3067_bbox(wgs84_bbox: list[float]) -> list[float]:
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    minx, miny = t.transform(wgs84_bbox[1], wgs84_bbox[0])
    maxx, maxy = t.transform(wgs84_bbox[3], wgs84_bbox[2])
    return [minx, miny, maxx, maxy]


def tile_bbox_to_3067(bbox_3067: list[float], row: int, col: int) -> list[float]:
    xmin = bbox_3067[0] + col * TILE_SIZE_M
    xmax = xmin + TILE_SIZE_M
    ymin = bbox_3067[1] + row * TILE_SIZE_M
    ymax = ymin + TILE_SIZE_M
    return [xmin, ymin, xmax, ymax]


def tile_intersects_buffer(tile_bbox: list[float], buffer_3067) -> bool:
    from shapely.geometry import box
    tile_poly = box(*tile_bbox)
    return tile_poly.intersects(buffer_3067)


def fetch_single_tile(tile_bbox: list[float], row: int, col: int) -> str | None:
    """Submit one MML DEM job for a tile bbox, poll, download. Returns tile filename or None."""
    label = f"tile_{row}_{col}"
    body = json.dumps({
        "id": PROCESS_ID,
        "inputs": {
            "boundingBoxInput": tile_bbox,
            "fileFormatInput": "TIFF",
        },
    })
    url = f"{MML_DEM_PROC}/processes/{PROCESS_ID}/execution"
    try:
        resp = requests.post(url, data=body, auth=(MML_KEY, ""), timeout=30,
                             headers={"Content-Type": "application/json"})
    except requests.RequestException as e:
        print(f"  {label}: submit failed — {e}")
        return None
    if resp.status_code == 401:
        print(f"  {label}: API key rejected (skip)")
        return None
    if resp.status_code != 201:
        print(f"  {label}: submit error {resp.status_code}")
        return None

    job_id = resp.json()["jobID"]
    status_url = f"{MML_DEM_PROC}/jobs/{job_id}"

    # Poll
    ok = False
    for i in range(POLL_MAX):
        time.sleep(POLL_INTERVAL)
        try:
            status = requests.get(status_url, auth=(MML_KEY, ""), timeout=30).json()
        except Exception:
            continue
        st = status["status"]
        if st == "successful":
            ok = True
            break
        if st in ("failed", "error"):
            print(f"  {label}: job failed — {status.get('message', 'unknown')}")
            return None
    if not ok:
        print(f"  {label}: timeout after {POLL_MAX * POLL_INTERVAL}s")
        return None

    # Download
    try:
        results = requests.get(f"{MML_DEM_PROC}/jobs/{job_id}/results",
                               auth=(MML_KEY, ""), timeout=30).json()
    except Exception as e:
        print(f"  {label}: results fetch failed — {e}")
        return None

    dl_url = None
    for entry in results.get("results", []):
        if isinstance(entry, dict) and entry.get("path"):
            dl_url = entry["path"]
            break
    if not dl_url:
        print(f"  {label}: no download URL in results")
        return None

    try:
        r = requests.get(dl_url, auth=(MML_KEY, ""), timeout=600)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  {label}: download failed — {e}")
        return None

    fname = f"{AOI_CITY}_FINLAND_mml_dem_2m_tile_{row}_{col}.tiff"
    out = TILES_DIR / fname
    with open(out, "wb") as f:
        f.write(r.content)
    mb = len(r.content) / 1e6
    print(f"  {label}: {mb:.1f} MB — saved")
    return fname


def main():
    if not MML_KEY:
        print("ERROR: MML_KEY not found in config/keys.json or env.")
        sys.exit(1)

    TILES_DIR.mkdir(parents=True, exist_ok=True)

    # AOI bbox in EPSG:3067
    bbox_3067 = wgs84_to_3067_bbox(AOI_BBOX_WGS84)
    cols = math.ceil((bbox_3067[2] - bbox_3067[0]) / TILE_SIZE_M)
    rows = math.ceil((bbox_3067[3] - bbox_3067[1]) / TILE_SIZE_M)
    print(f"DEM grid: {cols}×{rows} tiles ({TILE_SIZE_M//1000}km × {TILE_SIZE_M//1000}km each)")

    # Reproject AOI buffer to EPSG:3067 for intersection checks
    from shapely.ops import transform as shp_transform
    from pyproj import Transformer
    _to_3067 = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True).transform
    buffer_3067 = shp_transform(_to_3067, AOI_BUFFER_POLY)

    # Build list of (row, col, bbox) for tiles intersecting the AOI buffer
    tiles = []
    for r in range(rows):
        for c in range(cols):
            tb = tile_bbox_to_3067(bbox_3067, r, c)
            if tile_intersects_buffer(tb, buffer_3067):
                tiles.append((r, c, tb))

    print(f"Tiles intersecting buffer: {len(tiles)}")
    if not tiles:
        print("No tiles to fetch — AOI buffer covers no land?")
        sys.exit(0)

    # Fetch concurrently
    submitted = 0
    completed = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fut_to_tile = {pool.submit(fetch_single_tile, tb, r, c): (r, c)
                       for r, c, tb in tiles}
        for fut in as_completed(fut_to_tile):
            r, c = fut_to_tile[fut]
            submitted += 1
            result = fut.result()
            if result:
                completed += 1
            else:
                failed += 1
            status = "OK" if result else "FAIL"
            print(f"  [{submitted}/{len(tiles)}] tile_{r}_{c}: {status}")

    total_mb = sum(f.stat().st_size for f in TILES_DIR.iterdir() if f.suffix == ".tiff") / 1e6
    print(f"\nDEM tiles: {completed} OK, {failed} failed, {total_mb:.1f} MB total")
    print(f"  Saved to: {TILES_DIR}")


if __name__ == "__main__":
    main()

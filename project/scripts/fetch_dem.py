"""
Fetch Digital Elevation Model (2m resolution) from MML OGC API Processes.

Source: MML OGC API Processes (requires MML_KEY in config/keys.json)
Native CRS: EPSG:3067 (metric, Finnish standard)
Output: data/raw/{CITY}_FINLAND_dem_2m.tiff (EPSG:3067)

Note: MML caps each job at 100 km². The script auto-clips to the AOI
      center within this limit. Set MML_KEY in config/keys.json.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from scripts.config import AOI_BBOX_WGS84, AOI_CITY, MML_KEY

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TARGET_CRS = "EPSG:3067"
MAX_AREA_KM2 = 90  # MML limit is 100 km², leave margin
POLL_INTERVAL = 5  # seconds between job status polls
POLL_MAX = 60  # max poll iterations (5 min total)

PROC_URL = "https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1"
PROCESS_ID = "korkeusmalli_2m_bbox"


def wgs84_to_3067_bbox(wgs84_bbox: list[float]) -> list[float]:
    """Convert [min_lat, min_lon, max_lat, max_lon] → [xmin, ymin, xmax, ymax] in EPSG:3067."""
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    minx, miny = transformer.transform(wgs84_bbox[1], wgs84_bbox[0])
    maxx, maxy = transformer.transform(wgs84_bbox[3], wgs84_bbox[2])
    return [minx, miny, maxx, maxy]


def clip_bbox_to_max_area(bbox_3067: list[float]) -> list[float]:
    """Clip bbox to MAX_AREA_KM², centered on the AOI centroid."""
    cx = (bbox_3067[0] + bbox_3067[2]) / 2
    cy = (bbox_3067[1] + bbox_3067[3]) / 2
    area_km2 = (bbox_3067[2] - bbox_3067[0]) * (bbox_3067[3] - bbox_3067[1]) / 1e6
    if area_km2 <= MAX_AREA_KM2:
        return bbox_3067
    half = (MAX_AREA_KM2 * 1e6) ** 0.5 / 2
    return [cx - half, cy - half, cx + half, cy + half]


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not MML_KEY:
        print(
            "ERROR: MML_KEY not found.\n"
            "  Add it to config/keys.json or set the MML_KEY env var.\n"
            "  Get a free key at https://omatili.maanmittauslaitos.fi\n"
            '  Example: echo \'{"MML_KEY": "your-key"}\' > config/keys.json'
        )
        sys.exit(1)

    bbox_3067 = wgs84_to_3067_bbox(AOI_BBOX_WGS84)
    bbox_3067 = clip_bbox_to_max_area(bbox_3067)

    area_km2 = (bbox_3067[2] - bbox_3067[0]) * (bbox_3067[3] - bbox_3067[1]) / 1e6
    print(f"DEM area: {area_km2:.1f} km² (centered on AOI centroid)")
    print(f"  Bbox:   {bbox_3067}")

    # Step 1: Submit async job
    body = json.dumps({
        "id": PROCESS_ID,
        "inputs": {
            "boundingBoxInput": bbox_3067,
            "fileFormatInput": "TIFF",
        },
    })

    url = f"{PROC_URL}/processes/{PROCESS_ID}/execution"
    print("Submitting DEM extraction job...")
    resp = requests.post(
        url,
        data=body,
        auth=(MML_KEY, ""),
        timeout=30,
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code == 401:
        print("  ERROR: MML API key rejected.")
        sys.exit(1)
    if resp.status_code != 201:
        print(f"  ERROR {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)

    job_id = resp.json()["jobID"]
    print(f"  Job ID: {job_id}")

    # Step 2: Poll until successful
    status_url = f"{PROC_URL}/jobs/{job_id}"
    for i in range(POLL_MAX):
        time.sleep(POLL_INTERVAL)
        status = requests.get(status_url, auth=(MML_KEY, ""), timeout=30).json()
        st = status["status"]
        print(f"  [{i * POLL_INTERVAL}s] Status: {st}")
        if st == "successful":
            break
        if st in ("failed", "error"):
            print(f"  ERROR: Job failed: {status.get('message', 'unknown')}")
            sys.exit(1)
    else:
        print("  ERROR: Job did not complete within timeout.")
        sys.exit(1)

    # Step 3: Get download URL from results
    results = requests.get(
        f"{PROC_URL}/jobs/{job_id}/results",
        auth=(MML_KEY, ""),
        timeout=30,
    ).json()

    # Find the href — structure: {"output1": {"href": "...", "type": "..."}, ...}
    dl_url = None
    for v in results.values():
        if isinstance(v, dict) and v.get("href"):
            dl_url = v["href"]
            break

    if not dl_url:
        print(f"  ERROR: No download URL in results: {json.dumps(results, indent=2)[:300]}")
        sys.exit(1)

    # Step 4: Download
    print(f"Downloading DEM...")
    r = requests.get(dl_url, auth=(MML_KEY, ""), timeout=600)
    r.raise_for_status()

    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_dem_2m.tiff"
    with open(out_path, "wb") as f:
        f.write(r.content)

    mb = len(r.content) / 1e6
    print(f"  Size:   {mb:.1f} MB")
    print(f"  CRS:    {TARGET_CRS} (native)")
    print(f"  Saved:  {out_path.name}")


if __name__ == "__main__":
    main()

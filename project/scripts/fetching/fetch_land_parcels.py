"""Fetch land parcels (kiinteistöt) from MML OGC API Features.
Output: EPSG:4326 GeoJSON. Filters to >= 10 ha.

MML returns geometry in EPSG:3067 (metres); we reproject to 4326 for
GeoJSON spec compliance so ArcGIS/QGIS can display it correctly."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY, MML_KEY, MML_PARCELS

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
PAGE_LIMIT = 10000
MIN_AREA_HA = 10
_PARALLEL = 4  # concurrent page requests

COLLECTION = "PalstanSijaintitiedot"

# MML returns EPSG:3067; reproject back to 4326 for valid GeoJSON
_TO_WGS84 = Transformer.from_crs("EPSG:3067", "EPSG:4326", always_xy=True).transform


def wgs84_to_3067_bbox_str(wgs84_bbox: list[float]) -> str:
    """Convert [min_lat, min_lon, max_lat, max_lon] to EPSG:3067 bbox coords."""
    t = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    minx, miny = t.transform(wgs84_bbox[1], wgs84_bbox[0])
    maxx, maxy = t.transform(wgs84_bbox[3], wgs84_bbox[2])
    return f"{minx:.1f},{miny:.1f},{maxx:.1f},{maxy:.1f}"


def to_4326_json(geom_3067: dict) -> dict:
    """Convert a GeoJSON geometry dict from EPSG:3067 to EPSG:4326."""
    s = shape(geom_3067)
    s_wgs84 = transform(_TO_WGS84, s)
    return mapping(s_wgs84)


def fetch_large_parcels(bbox_3067: str) -> list[dict]:
    """Paginate MML parcels in parallel, keep only >= MIN_AREA_HA."""
    all_large: list[dict] = []
    seen_ids: set[str] = set()
    crs_param = "http://www.opengis.net/def/crs/EPSG/0/3067"

    first_url = (
        f"{MML_PARCELS}/collections/{COLLECTION}/items"
        f"?bbox={bbox_3067}"
        f"&bbox-crs={crs_param}"
        f"&crs={crs_param}"
        f"&limit={PAGE_LIMIT}"
    )

    # Count total matching features via HEAD (OGC-NumberMatched header)
    head_resp = requests.head(first_url, auth=(MML_KEY or "", ""), timeout=30)
    total = int(head_resp.headers.get("OGC-NumberMatched", 0))
    limit = int(head_resp.headers.get("OGC-NumberReturned", PAGE_LIMIT))
    if limit > PAGE_LIMIT:
        limit = PAGE_LIMIT
    if total == 0:
        print("  No parcels in AOI")
        return []

    pages = (total + limit - 1) // limit
    print(f"  Total: {total:,} parcels, {pages} pages of {limit}")

    # Build page URLs
    urls = [first_url]
    for _ in range(1, pages):
        offset = f"&offset={_ * limit}"
        urls.append(first_url + offset)

    def fetch_and_process(url: str) -> int:
        resp = requests.get(url, auth=(MML_KEY or "", ""), timeout=120)
        if resp.status_code == 401:
            sys.exit("  ERROR: MML API key rejected.")
        if resp.status_code != 200:
            return 0
        feats = resp.json().get("features", [])
        kept = 0
        for f in feats:
            g = f.get("geometry")
            if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            try:
                s_3067 = shape(g)
                ha = s_3067.area / 10000
                pid = f.get("properties", {}).get("kiinteistotunnus", "")
                if ha >= MIN_AREA_HA and pid not in seen_ids:
                    seen_ids.add(pid)
                    f["geometry"] = to_4326_json(g)
                    f["properties"]["area_ha"] = round(ha, 1)
                    all_large.append(f)
                    kept += 1
            except Exception:
                pass
        return kept

    with ThreadPoolExecutor(max_workers=_PARALLEL) as pool:
        futs = {pool.submit(fetch_and_process, u): u for u in urls}
        done = 0
        for fut in as_completed(futs):
            done += 1
            if done % 20 == 0 or done == len(urls):
                print(f"  {done}/{len(urls)} pages — {len(all_large)} kept")

    print(f"  Total: {len(all_large)} parcels >= {MIN_AREA_HA} ha")
    return all_large


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

    bbox_3067 = wgs84_to_3067_bbox_str(AOI_BBOX_WGS84)
    parts = [float(v) for v in bbox_3067.split(",")]
    area_km2 = (parts[2] - parts[0]) * (parts[3] - parts[1]) / 1e6

    print(f"Fetching land parcels for AOI (~{area_km2:.0f} km²)...")

    large_parcels = fetch_large_parcels(bbox_3067)

    if not large_parcels:
        print("  No parcels >= 10 ha found.")
        sys.exit(0)

    fc = {"type": "FeatureCollection", "features": large_parcels}
    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_mml_land_parcels.geojson"
    out_path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    areas = [f["properties"]["area_ha"] for f in large_parcels]

    print(f"\n  Parcels >= 10 ha:  {len(large_parcels)}")
    print(f"  Largest:           {max(areas):.0f} ha")
    print(f"  Saved:             {out_path.name}")


if __name__ == "__main__":
    main()

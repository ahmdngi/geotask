"""Fetch land parcels (kiinteistöt) from MML OGC API Features.
Output: EPSG:4326 GeoJSON. Filters to >= 10 ha.

MML returns geometry in EPSG:3067 (metres); we reproject to 4326 for
GeoJSON spec compliance so ArcGIS/QGIS can display it correctly."""

import json
import sys
import time
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
PAGE_LIMIT = 1000
MIN_AREA_HA = 10

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
    """Paginate MML parcels, keep only >= MIN_AREA_HA on-the-fly."""
    all_large = []
    seen_ids = set()
    skipped_null = 0
    skipped_small = 0
    crs_param = "http://www.opengis.net/def/crs/EPSG/0/3067"

    url = (
        f"{MML_PARCELS}/collections/{COLLECTION}/items"
        f"?bbox={bbox_3067}"
        f"&bbox-crs={crs_param}"
        f"&crs={crs_param}"
        f"&limit={PAGE_LIMIT}"
    )

    page = 0
    while url:
        page += 1
        resp = requests.get(url, auth=(MML_KEY or "", ""), timeout=120)
        if resp.status_code == 401:
            print("  ERROR: MML API key rejected.")
            sys.exit(1)
        if resp.status_code != 200:
            print(f"  MML error {resp.status_code} on page {page}: {resp.text[:200]}")
            break

        data = resp.json()
        features = data.get("features", [])
        if not features:
            break

        kept = 0
        for f in features:
            g = f.get("geometry")
            if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
                skipped_null += 1
                continue
            try:
                s_3067 = shape(g)
                ha = s_3067.area / 10000          # coords are in metres → sq m → ha
                pid = f.get("properties", {}).get("kiinteistotunnus", "")
                if ha >= MIN_AREA_HA and pid not in seen_ids:
                    seen_ids.add(pid)
                    f["geometry"] = to_4326_json(g)   # reproject for GeoJSON
                    f["properties"]["area_ha"] = round(ha, 1)
                    all_large.append(f)
                    kept += 1
                else:
                    skipped_small += 1
            except Exception:
                pass

        if kept == 0 and page >= 3:
            print(f"  Page {page}: {len(features)} feats, 0 kept — stopping (no >=10 ha parcels in first 3 pages)")
            break

        print(f"  Page {page}: {len(features)} feats -> {kept} kept (total: {len(all_large)})")

        url = None
        for link in data.get("links", []):
            if link.get("rel") == "next":
                url = link["href"]
                break
        time.sleep(0.3)

    print(f"  Skipped: {skipped_null} null-geom, {skipped_small} < {MIN_AREA_HA} ha")
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

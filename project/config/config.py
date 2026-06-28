"""
Shared configuration loader for KRIOS GIS data fetching scripts.

Reads from:
  - config/aoi.json   (AOI city center + buffer radius)
  - config/keys.json  (API keys, fallback to env vars)
  - Environment variables (override keys.json)

Provides:
  AOI_CITY, AOI_CENTER_WGS84, AOI_BUFFER_KM
  AOI_BBOX_WGS84    (bounding box of the buffer — for API queries)
  AOI_BUFFER_POLY   (the actual circular buffer polygon in WGS84)
"""

import json
import os
import sys
from pathlib import Path

import pyproj
from shapely.geometry import Point
from shapely.ops import transform

# Allow loading complex/large GeoJSON features (nature reserves, etc.)
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

# Make project root importable when running scripts directly
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CONFIG_DIR = _PROJECT_ROOT / "config"
_DATA_DIR = _PROJECT_ROOT / "data"
_ETL_DIR = _DATA_DIR / "etl"

# ── CRS definitions ──────────────────────────────────────────────────
WGS84 = pyproj.CRS("EPSG:4326")
ETRS = pyproj.CRS("EPSG:3067")
_PROJ_FWD = pyproj.Transformer.from_crs(WGS84, ETRS, always_xy=True).transform
_PROJ_REV = pyproj.Transformer.from_crs(ETRS, WGS84, always_xy=True).transform


def _load_json(name: str) -> dict:
    path = _CONFIG_DIR / name
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def get_aoi() -> dict:
    """Return AOI config dict with keys: city, center_wgs84, buffer_km."""
    aoi = _load_json("aoi.json")
    return {
        "city": aoi.get("city", "Helsinki"),
        "center_wgs84": aoi.get("center_wgs84", [60.1666, 24.9435]),
        "buffer_km": aoi.get("buffer_km", 100),
    }


def build_buffer_polygon(center_wgs84: list[float], buffer_km: float):
    """Create a circular buffer polygon in WGS84 around center."""
    p_wgs84 = Point(center_wgs84[1], center_wgs84[0])
    cx, cy = _PROJ_FWD(p_wgs84.x, p_wgs84.y)
    circle_3067 = Point(cx, cy).buffer(buffer_km * 1000)
    return transform(_PROJ_REV, circle_3067)


def get_bbox_from_buffer(buffer_poly) -> list[float]:
    """Return [min_lat, min_lon, max_lat, max_lon] from buffer bounds."""
    lomin, lamin, lomax, lamax = buffer_poly.bounds
    return [lamin, lomin, lamax, lomax]


def get_key(name: str) -> str:
    """Get API key: env var > keys.json > empty string."""
    env_val = os.environ.get(name)
    if env_val:
        return env_val
    keys = _load_json("keys.json")
    return keys.get(name, "")


def set_aoi(city: str, center_wgs84: list[float], buffer_km: float):
    """Write AOI config to disk so all scripts see it."""
    data = {
        "city": city,
        "center_wgs84": center_wgs84,
        "buffer_km": buffer_km,
        "description": f"{buffer_km}km buffer around {city} center ({center_wgs84[0]:.4f}, {center_wgs84[1]:.4f})",
    }
    path = _CONFIG_DIR / "aoi.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"AOI set: {city} — {buffer_km}km buffer around ({center_wgs84[0]:.4f}, {center_wgs84[1]:.4f})")


# ── Module-level convenience exports ─────────────────────────────────
_AOI = get_aoi()
AOI_CITY: str = _AOI["city"]
AOI_CENTER_WGS84: list[float] = _AOI["center_wgs84"]
AOI_BUFFER_KM: float = _AOI["buffer_km"]

# Build the circular buffer polygon
AOI_BUFFER_POLY = build_buffer_polygon(AOI_CENTER_WGS84, AOI_BUFFER_KM)

# Derive the bbox from the buffer (for API queries that only accept bbox)
AOI_BBOX_WGS84: list[float] = get_bbox_from_buffer(AOI_BUFFER_POLY)

MML_KEY: str = get_key("MML_KEY")

# Save buffer to GeoJSON so scripts & maps can load it
if not (_DATA_DIR / "raw" / "buffer.geojson").exists() or True:  # always refresh
    import json as _json
    from shapely.geometry import mapping as _mapping

    _ETL_DIR.mkdir(parents=True, exist_ok=True)
    _buffer_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": _mapping(AOI_BUFFER_POLY),
                "properties": {
                    "city": AOI_CITY,
                    "center_lat": AOI_CENTER_WGS84[0],
                    "center_lon": AOI_CENTER_WGS84[1],
                    "buffer_km": AOI_BUFFER_KM,
                },
            }
        ],
    }
    _buffer_path = _ETL_DIR / f"{AOI_CITY}_FINLAND_buffer.geojson"
    with open(_buffer_path, "w", encoding="utf-8") as _f:
        _json.dump(_buffer_fc, _f, ensure_ascii=False)

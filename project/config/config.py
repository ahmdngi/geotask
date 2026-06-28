"""
Shared configuration.

Reads from:
  - config/aoi.json   (AOI center + buffer)
  - config/keys.json  (API keys, fallback to env vars)
"""

import json, os, sys
from pathlib import Path
import pyproj
from shapely.geometry import Point
from shapely.ops import transform

os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CONFIG_DIR = _PROJECT_ROOT / "config"
_DATA_DIR = _PROJECT_ROOT / "data"
_ETL_DIR = _DATA_DIR / "etl"

# ── CRS ──
WGS84 = pyproj.CRS("EPSG:4326")
ETRS = pyproj.CRS("EPSG:3067")
_PROJ_FWD = pyproj.Transformer.from_crs(WGS84, ETRS, always_xy=True).transform
_PROJ_REV = pyproj.Transformer.from_crs(ETRS, WGS84, always_xy=True).transform

# ── API endpoints ──
FINGRID_BASE = "https://services2.arcgis.com/uh3cDCipmuPcmxmx/ArcGIS/rest/services"
OVERPAST_URL = "https://overpass-api.de/api/interpreter"
MML_PARCELS = "https://avoin-paikkatieto.maanmittauslaitos.fi/kiinteisto-avoin/simple-features/v3"
MML_DEM_PROC = "https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1"
SYKE_WFS = "https://paikkatiedot.ymparisto.fi/geoserver"
EEA_NATURA = "https://bio.discomap.eea.europa.eu/arcgis/rest/services/ProtectedSites/Natura2000Sites/MapServer/0"
DATACENTERMAP = "https://www.datacentermap.com"
MML_SIGNUP = "https://omatili.maanmittauslaitos.fi"

# ── File helpers ──
def _load_json(name: str) -> dict:
    path = _CONFIG_DIR / name
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def get_aoi() -> dict:
    aoi = _load_json("aoi.json")
    return {
        "city": aoi.get("city", "Helsinki"),
        "center_wgs84": aoi.get("center_wgs84", [60.1666, 24.9435]),
        "buffer_km": aoi.get("buffer_km", 100),
    }

def build_buffer_polygon(center_wgs84: list[float], buffer_km: float):
    p = Point(center_wgs84[1], center_wgs84[0])
    cx, cy = _PROJ_FWD(p.x, p.y)
    return transform(_PROJ_REV, Point(cx, cy).buffer(buffer_km * 1000))

def get_bbox_from_buffer(buffer_poly) -> list[float]:
    lomin, lamin, lomax, lamax = buffer_poly.bounds
    return [lamin, lomin, lamax, lomax]

def get_key(name: str) -> str:
    env_val = os.environ.get(name)
    if env_val:
        return env_val
    return _load_json("keys.json").get(name, "")

def set_aoi(city: str, center_wgs84: list[float], buffer_km: float):
    data = {
        "city": city,
        "center_wgs84": center_wgs84,
        "buffer_km": buffer_km,
        "description": f"{buffer_km}km buffer around {city}",
    }
    path = _CONFIG_DIR / "aoi.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"AOI set: {city} — {buffer_km}km buffer")

# ── Convenience exports ──
_AOI = get_aoi()
AOI_CITY = _AOI["city"]
AOI_CENTER_WGS84 = _AOI["center_wgs84"]
AOI_BUFFER_KM = _AOI["buffer_km"]
AOI_BUFFER_POLY = build_buffer_polygon(AOI_CENTER_WGS84, AOI_BUFFER_KM)
AOI_BBOX_WGS84 = get_bbox_from_buffer(AOI_BUFFER_POLY)
MML_KEY = get_key("MML_KEY")

# Save buffer GeoJSON
import json as _json
from shapely.geometry import mapping as _mapping
_ETL_DIR.mkdir(parents=True, exist_ok=True)
_json.dump({
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": _mapping(AOI_BUFFER_POLY),
        "properties": {"city": AOI_CITY, "buffer_km": AOI_BUFFER_KM},
    }]
}, open(_ETL_DIR / f"{AOI_CITY}_FINLAND_buffer.geojson", "w"), ensure_ascii=False)

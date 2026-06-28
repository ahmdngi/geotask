"""
Shared configuration loader for KRIOS GIS data fetching scripts.

Reads from:
  - config/aoi.json   (AOI bbox + city name)
  - config/keys.json  (API keys, fallback to env vars)
  - Environment variables (override keys.json)
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Make project root importable when running scripts directly
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CONFIG_DIR = _PROJECT_ROOT / "config"


def _load_json(name: str) -> dict:
    path = _CONFIG_DIR / name
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def get_aoi() -> dict:
    """Return AOI config dict with keys: city, bbox_wgs84."""
    aoi = _load_json("aoi.json")
    return {
        "city": aoi.get("city", "Helsinki"),
        "bbox_wgs84": aoi.get("bbox_wgs84", [59.7, 23.9, 60.7, 26.0]),
    }


def get_key(name: str) -> str:
    """Get API key: env var > keys.json > empty string."""
    env_val = os.environ.get(name)
    if env_val:
        return env_val
    keys = _load_json("keys.json")
    return keys.get(name, "")


def set_aoi(city: str, bbox_wgs84: list[float]):
    """Write AOI config to disk so all scripts see it."""
    data = {
        "city": city,
        "bbox_wgs84": bbox_wgs84,
        "description": f"[min_lat, min_lon, max_lat, max_lon] — {city} area",
    }
    path = _CONFIG_DIR / "aoi.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"AOI set: {city} — bbox {bbox_wgs84}")


# ── Convenience globals ──────────────────────────────────────────────
AOI = get_aoi()
AOI_BBOX_WGS84: list[float] = AOI["bbox_wgs84"]
AOI_CITY: str = AOI["city"]
MML_KEY: str = get_key("MML_KEY")

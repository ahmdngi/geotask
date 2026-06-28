#!/usr/bin/env python3
"""
Orchestrator: run all data-fetching scripts for the selected AOI city.

Usage:
  python scripts/run_all.py                    # fetch all layers
  python scripts/run_all.py --fingrid --osm     # fetch only specified
  python scripts/run_all.py --skip-dem          # skip DEM (takes long)

Config:
  - AOI city/bbox read from config/aoi.json
  - API keys read from config/keys.json
  - Run city_picker.py first to set the AOI interactively
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts" / "fetching"

ALL_SCRIPTS = [
    "fetch_fingrid.py",
    "fetch_osm.py",
    "fetch_urban_centers.py",
    "fetch_natura2000.py",
    "fetch_flood_zones.py",
    "fetch_nature_reserves.py",
    "fetch_land_parcels.py",
    "fetch_dem.py",
]


def run_script(name: str) -> dict:
    """Run a single fetch script and return timing + exit info."""
    script_path = _SCRIPTS_DIR / name
    if not script_path.exists():
        return {"script": name, "status": "SKIP", "error": "not found", "seconds": 0}

    t0 = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=600,
    )
    elapsed = time.time() - t0

    if result.returncode == 0:
        return {"script": name, "status": "OK", "output": result.stdout, "seconds": elapsed}
    else:
        return {
            "script": name,
            "status": "FAIL",
            "output": result.stdout,
            "error": result.stderr[:500],
            "seconds": elapsed,
        }


def main():
    parser = argparse.ArgumentParser(description="Run all KRIOS data-fetching scripts.")
    parser.add_argument("--skip", nargs="*", default=[], help="Scripts to skip (e.g. --skip dem)")
    parser.add_argument(
        "--only", nargs="*", default=[],
        help="Only run these (e.g. --only fingrid osm). Overrides --skip."
    )
    args = parser.parse_args()

    # Show current AOI
    aoi_path = _PROJECT_ROOT / "config" / "aoi.json"
    if aoi_path.exists():
        import json
        aoi = json.loads(aoi_path.read_text())
        print(f"📍 AOI: {aoi.get('city', '?')} — bbox: {aoi.get('bbox_wgs84', '?')}")
        print(f"   Edit config/aoi.json or run city_picker.py to change.\n")
    else:
        print("⚠️  No config/aoi.json found. Using default Helsinki AOI.\n")

    # Filter scripts
    to_run = ALL_SCRIPTS.copy()
    if args.only:
        to_run = [s for s in to_run if any(s.startswith(f"fetch_{o}") for o in args.only)]
    if args.skip:
        to_run = [s for s in to_run if not any(s.startswith(f"fetch_{o}") for o in args.skip)]

    if not to_run:
        print("No scripts to run after filters.")
        sys.exit(0)

    print(f"🚀 Running {len(to_run)} scripts...\n")

    results = []
    for name in to_run:
        print(f"── {name} ──", flush=True)
        r = run_script(name)
        results.append(r)

        if r["status"] == "OK" and r["output"]:
            # Show last 3 lines of output per script
            lines = [l for l in r["output"].split("\n") if l.strip()]
            for line in lines[-3:]:
                print(f"  {line}")
        elif r["status"] == "FAIL":
            print(f"  ❌ {r.get('error', 'unknown error')}")

        print(f"  ({r['seconds']:.1f}s)\n")

    # Summary
    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    total = sum(r["seconds"] for r in results)

    print("═" * 50)
    print(f"  ✅ {ok_count}/{len(results)} scripts succeeded")
    if fail_count:
        print(f"  ❌ {fail_count} failed")
        for r in results:
            if r["status"] == "FAIL":
                print(f"     - {r['script']}: {r.get('error', '')[:100]}")
    print(f"  ⏱  {total:.1f}s total")
    print(f"  📁 Output: {_PROJECT_ROOT / 'data' / 'raw'}/")


if __name__ == "__main__":
    main()

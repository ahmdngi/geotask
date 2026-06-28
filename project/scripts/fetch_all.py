"""
Run all data-fetching scripts for the selected AOI city.

Usage:
  python scripts/fetch_all.py                    # fetch all
  python scripts/fetch_all.py --skip dem         # skip DEM
  python scripts/fetch_all.py --only fingrid     # specific only
"""

import argparse, os, subprocess, sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts" / "fetching"

ALL_SCRIPTS = [
    "fetch_fingrid.py", "fetch_osm.py", "fetch_urban_centers.py",
    "fetch_natura2000.py", "fetch_flood_zones.py", "fetch_nature_reserves.py",
    "fetch_land_parcels.py", "fetch_datacentermap.py", "fetch_dem.py",
]


def run(name: str) -> dict:
    sp = SCRIPTS_DIR / name
    if not sp.exists():
        return {"name": name, "status": "SKIP"}
    t0 = time.time()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    print(f"\n{'─'*50}\n  [{name}]\n{'─'*50}")
    try:
        r = subprocess.run([sys.executable, str(sp)], timeout=1800, env=env)
        elapsed = time.time() - t0
        if r.returncode == 0:
            return {"name": name, "status": "OK", "time": elapsed}
        return {"name": name, "status": "FAIL", "error": f"exit code {r.returncode}", "time": elapsed}
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "TIMEOUT", "time": time.time() - t0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip", nargs="*", default=[])
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    aoi_path = ROOT / "config" / "aoi.json"
    if aoi_path.exists():
        aoi = json.loads(aoi_path.read_text())
        print(f"AOI: {aoi.get('city', '?')}")

    to_run = ALL_SCRIPTS.copy()
    if args.only:
        to_run = [s for s in to_run if any(s.startswith(f"fetch_{o}") for o in args.only)]
    if args.skip:
        to_run = [s for s in to_run if not any(s.startswith(f"fetch_{o}") for o in args.skip)]

    results = [run(s) for s in to_run]

    print(f"\n{'='*50}")
    ok = sum(1 for r in results if r["status"] == "OK")
    fail = sum(1 for r in results if r["status"] != "OK")
    print(f"  {ok}/{len(results)} passed" + (f"  ❌ {fail} failed" if fail else ""))
    for r in results:
        if r["status"] != "OK":
            print(f"    {r['name']}: {r.get('error','')[:100]}")
    total = sum(r.get("time", 0) for r in results)
    print(f"  {total:.0f}s total")
    print(f"{'='*50}")

    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()

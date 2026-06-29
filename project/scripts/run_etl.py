"""
Orchestrator — run all ETL steps in order.

Usage:
  python scripts/run_etl.py              # run all steps
  python scripts/run_etl.py --skip qc    # skip specific steps
"""

import subprocess
import sys
import time
from pathlib import Path

ETL_DIR = Path(__file__).resolve().parent / "etl"
ROOT = ETL_DIR.parent

STEPS = [
    ("Finland boundary", [sys.executable, str(ETL_DIR / "fetch_finland_boundary.py")]),
    ("Process DEM tiles", [sys.executable, str(ETL_DIR / "process_dem_tiles.py")]),
    ("Clip to AOI", [sys.executable, str(ETL_DIR / "clip_to_aoi.py")]),
    ("Merge exclusions", [sys.executable, str(ETL_DIR / "merge_exclusions.py")]),
    ("QC Report", [sys.executable, str(ETL_DIR / "qc_report.py")]),
    ("Score parcels", [sys.executable, str(ROOT / "scoring" / "score_parcels.py")]),
]


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"\n{'=' * 60}")
    print(f"  [{name}]")
    print(f"{'=' * 60}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT, capture_output=False)
    elapsed = time.time() - t0
    success = result.returncode == 0
    status = "✅" if success else "❌"
    print(f"  {status} {name} ({elapsed:.1f}s)")
    return success


def main():
    skip_list = set()
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--skip" and i + 1 < len(args):
            skip_list.add(args[i + 1].lower())
            i += 2
        else:
            i += 1

    all_ok = True
    for name, cmd in STEPS:
        skip_key = name.lower().split()[0]
        if skip_key in skip_list:
            print(f"  SKIP: {name}")
            continue
        if not run_step(name, cmd):
            all_ok = False
            print(f"  WARNING: {name} failed — continuing...")

    print(f"\n{'=' * 60}")
    if all_ok:
        print("  ✅ All ETL steps completed successfully")
    else:
        print("  ⚠️  Some ETL steps had errors (see above)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

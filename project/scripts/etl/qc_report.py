"""
QC Report — validate CRS, geometry, feature counts for all data layers.
"""

import sys
from pathlib import Path

import geopandas as gpd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY

RAW_DIR = ROOT / "data" / "raw"
CLIP_DIR = ROOT / "data" / "etl" / "clipped"
EXCL_DIR = ROOT / "data" / "etl" / "exclusions"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
ETL_DIR = ROOT / "data" / "etl"
TARGET_CRS = "EPSG:3067"
HEADER = f"""
{'='*70}
QC REPORT — {AOI_CITY}
{'='*70}
AOI bbox: {AOI_BBOX_WGS84}
"""


def check(path: Path, label: str) -> list[str]:
    issues = []
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        return [f"  ERROR: {e}"]
    count = len(gdf)
    issues.append(f"  Features: {count:,}")
    if count == 0:
        issues.append("  ⚠️  EMPTY")
        return issues

    crs = gdf.crs
    expected = "EPSG:4326" if path.suffix == ".geojson" else TARGET_CRS
    if crs is None:
        issues.append("  ❌ CRS: None")
    else:
        s = crs.to_string()
        issues.append(f"  {'✅' if s == expected else '❌'} CRS: {s}")

    issues.append(f"  Geom: {dict(gdf.geometry.geom_type.value_counts())}")

    nulls = gdf.geometry.isna().sum()
    if nulls:
        issues.append(f"  ❌ Null geom: {nulls}")
    invalid = (~gdf.geometry.is_valid).sum()
    if invalid:
        issues.append(f"  ⚠️  Invalid: {invalid}/{count}")

    for col in gdf.columns:
        if col == "geometry":
            continue
        n = gdf[col].isna().sum()
        if n > 0 and n / count > 0.5:
            issues.append(f"  ⚠️  {col}: {n}/{count} null ({n*100//count}%)")

    return issues


def main():
    lines = [HEADER]
    for label, d in [("Raw", RAW_DIR), ("Clipped", CLIP_DIR), ("Exclusions", EXCL_DIR), ("Suitability", SUIT_DIR)]:
        if not d.exists():
            continue
        files = sorted(d.glob("*.geojson"))
        if not files:
            continue
        lines.append(f"\n{'─'*70}\n{label} ({d.relative_to(ROOT)})\n{'─'*70}")
        for f in files:
            lines.append(f"\n📄 {f.name}")
            lines.extend(check(f, f.stem))

    total = sum(1 for _, d in [("", RAW_DIR), ("", CLIP_DIR), ("", EXCL_DIR), ("", SUIT_DIR)] if d.exists() for f in d.glob("*.geojson"))
    lines.append(f"\n{'─'*70}\nTotal: {total} layers")

    report = "\n".join(lines)
    print(report)
    ETL_DIR.mkdir(parents=True, exist_ok=True)
    (ETL_DIR / f"{AOI_CITY}_FINLAND_qc_report.txt").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()

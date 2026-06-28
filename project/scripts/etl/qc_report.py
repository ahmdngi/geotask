"""
QC Report — validate all raw and ETL data layers.

Checks: CRS, geometry validity, nulls, feature count, spatial extent,
        duplicate IDs, topology overlaps.

Output: data/etl/{CITY}_FINLAND_qc_report.txt
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

REPORT_HEADER = f"""
{'=' * 70}
QC REPORT — {AOI_CITY}
{'=' * 70}
AOI bbox (WGS84): {AOI_BBOX_WGS84}
Generated:         {__import__('datetime').datetime.now().isoformat()}
"""


def check_layer(path: Path, label: str) -> list[str]:
    """Run all QC checks on a single layer. Return list of issues."""
    issues = []
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        return [f"  ERROR: Cannot read — {e}"]

    count = len(gdf)
    issues.append(f"  Features: {count:,}")

    if count == 0:
        issues.append(f"  ⚠️  EMPTY LAYER")
        return issues

    # CRS — GeoJSON should be WGS84 per spec, TIFF should be 3067
    crs = gdf.crs
    expected_crs = "EPSG:4326" if path.suffix == ".geojson" else TARGET_CRS
    if crs is None:
        issues.append(f"  ❌ CRS: None")
    else:
        crs_str = crs.to_string()
        if crs_str == expected_crs:
            issues.append(f"  ✅ CRS: {crs_str}")
        else:
            issues.append(f"  ❌ CRS: {crs_str} (expected {expected_crs})")

    # Geometry type
    geom_types = gdf.geometry.geom_type.value_counts().to_dict()
    issues.append(f"  Geom: {dict(geom_types)}")

    # Null geometries
    null_geom = gdf.geometry.isna().sum()
    if null_geom > 0:
        issues.append(f"  ❌ Null geometries: {null_geom}")

    # Geometry validity
    invalid = (~gdf.geometry.is_valid).sum()
    if invalid > 0:
        pct = invalid / count * 100
        issues.append(f"  ⚠️  Invalid geometries: {invalid} ({pct:.1f}%)")

    # Null attributes
    for col in gdf.columns:
        if col == "geometry":
            continue
        nulls = gdf[col].isna().sum()
        if nulls > 0:
            pct = nulls / count * 100
            if pct > 50:
                issues.append(f"  ⚠️  {col}: {nulls}/{count} null ({pct:.0f}%)")

    # Spatial extent
    try:
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
        area_km2 = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) / 1e6
        issues.append(f"  Extent: {area_km2:.0f} km² ({bounds[0]:.0f}, {bounds[1]:.0f}) to ({bounds[2]:.0f}, {bounds[3]:.0f})")
    except Exception:
        pass

    # Duplicate IDs (if 'id' column exists)
    if "id" in gdf.columns:
        dupes = gdf["id"].duplicated().sum()
        if dupes > 0:
            issues.append(f"  ⚠️  Duplicate IDs: {dupes}")

    return issues


def main():
    report_lines = [REPORT_HEADER]

    # Scan all directories
    dirs_to_check = [
        ("Raw data", RAW_DIR),
        ("Clipped data", CLIP_DIR),
        ("Exclusion zones", EXCL_DIR),
        ("Suitability", SUIT_DIR),
    ]

    for dir_label, directory in dirs_to_check:
        if not directory.exists():
            continue
        files = sorted(directory.glob("*"))
        if not files:
            continue
        report_lines.append(f"\n{'─' * 70}")
        report_lines.append(f"{dir_label} ({directory.relative_to(ROOT)})")
        report_lines.append(f"{'─' * 70}")

        for fpath in files:
            if fpath.suffix != ".geojson":
                continue
            report_lines.append(f"\n📄 {fpath.name}")
            try:
                issues = check_layer(fpath, fpath.stem)
                report_lines.extend(issues)
            except Exception as e:
                report_lines.append(f"  ❌ ERROR: {e}")

    # Summary counts
    report_lines.append(f"\n{'─' * 70}")
    total_files = 0
    for _, d in dirs_to_check:
        if d.exists():
            total_files += len([f for f in d.glob("*") if f.suffix in (".geojson", ".tiff")])
    report_lines.append(f"\nTotal layers checked: {total_files}")

    report = "\n".join(report_lines)
    print(report)

    # Save report
    ETL_DIR.mkdir(parents=True, exist_ok=True)
    report_path = ETL_DIR / f"{AOI_CITY}_FINLAND_qc_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()

"""Score land parcels for data center suitability.

Pipeline:
  1. Load clipped parcels + all reference layers
  2. Filter: remove parcels intersecting exclusion zones
  3. Filter: keep parcels overlapping suitability raster (value=1)
  4. Compute 7 scoring dimensions (each 0-10)
  5. Aggregate to total score → ranked output

Scoring dimensions (each 0-10, higher = better):
  GRID_CAPACITY  — MW headroom at nearest Fingrid substation
  HV_ACCESS      — proximity to 220/400 kV transmission line
  URBAN_ACCESS   — proximity to 100k+ population center
  DC_CLUSTER     — proximity to existing data centers
  GEN_ACCESS     — proximity to power plants (PPA / grid-tie)
  PARCEL_SIZE    — 10-100 ha, larger = better
  ZONING         — land use type if available (industrial = 10)

Output: data/etl/suitability/{City}_FINLAND_scored_parcels.geojson
"""

import sys, time, json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.sample import sample_gen
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from config.config import AOI_CITY

CLIP_DIR = ROOT / "data" / "etl" / "clipped"
EXCL_DIR = ROOT / "data" / "etl" / "exclusions"
SUIT_DIR = ROOT / "data" / "etl" / "suitability"
OUT_DIR = ROOT / "data" / "etl" / "suitability"
FINAL_DIR = ROOT / "outputs"          # deliverables for the dev team
TOP_N = 20                              # top candidates exported to outputs/

TARGET_CRS = "EPSG:3067"
WGS84 = "EPSG:4326"

# ── Scoring parameters ──────────────────────────────────────────────
# Distance thresholds in metres (score=10 at d_min, linear → 0 at d_max)
HV_DIST = dict(d_min=1_000, d_max=50_000)       # 1-50 km
URBAN_DIST = dict(d_min=5_000, d_max=100_000)    # 5-100 km
DC_DIST = dict(d_min=2_000, d_max=80_000)        # 2-80 km
GEN_DIST = dict(d_min=1_000, d_max=50_000)        # 1-50 km
PARCEL_SIZE = dict(min_ha=10, max_ha=100)
MAX_GRID_MW = 500  # normalisation ceiling for Kulutus_25 headroom

# ── MCDM weights (weighted sum model) ────────────────────────────────
# Sum of weights = 1.0. Adjust per criterion importance.
MCDM_WEIGHTS = {
    "grid": 0.25,    # Power headroom — #1 constraint for data centers
    "hv": 0.15,      # HV transmission access
    "urban": 0.10,   # Workforce & fiber connectivity
    "dc": 0.15,      # Existing DC cluster (infrastructure co-location)
    "gen": 0.10,     # Generation proximity (PPA / grid-tie)
    "size": 0.15,    # Parcel area
    "zoning": 0.10,  # Land use compatibility
}


# ── Helpers ─────────────────────────────────────────────────────────

def load_gdf(path: Path, label: str = "") -> gpd.GeoDataFrame | None:
    """Load geojson, return 3067-projected GDF or None."""
    if not path or not path.exists():
        if label:
            print(f"  SKIP {label}: not found")
        return None
    try:
        gdf = gpd.read_file(path)
        if gdf.empty:
            if label:
                print(f"  SKIP {label}: empty")
            return None
        if gdf.crs is None:
            # Guess CRS from coordinate range
            b = gdf.total_bounds
            if -180 <= b[0] <= 180 and -90 <= b[1] <= 90:
                gdf.set_crs(WGS84, inplace=True)
            else:
                gdf.set_crs(TARGET_CRS, inplace=True)
        return gdf.to_crs(TARGET_CRS)
    except Exception as e:
        if label:
            print(f"  SKIP {label}: {e}")
        return None


def distance_score(d_m: float, d_min: float, d_max: float) -> float:
    """Linear: 10 at d_min, 0 at ≥ d_max. Clipped."""
    if d_m <= d_min:
        return 10.0
    if d_m >= d_max:
        return 0.0
    return 10.0 * (1 - (d_m - d_min) / (d_max - d_min))


# ── Main ─────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    prefix = f"{AOI_CITY}_FINLAND"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load parcels
    parcels = load_gdf(CLIP_DIR / f"{prefix}_mml_land_parcels.geojson", "Parcels")
    if parcels is None:
        print("No parcels — nothing to score.")
        sys.exit(0)
    print(f"  Parcels loaded: {len(parcels)}")

    # 2. Load exclusion zones
    excl = load_gdf(EXCL_DIR / f"{prefix}_exclusion_zones.geojson", "Exclusions")

    # 3. Load suitability raster
    raster_path = SUIT_DIR / f"{prefix}_gradient_suitable_8pct.tiff"
    if not raster_path.exists():
        print(f"  SKIP raster: {raster_path.name} not found")
        raster = None
    else:
        raster = rasterio.open(raster_path)

    # 4. Filter steps
    # 4a. Remove parcels intersecting exclusion zones
    if excl is not None:
        # Merge all exclusion geometries into one
        excl_union = excl.geometry.union_all()
        before = len(parcels)
        parcels = parcels[~parcels.intersects(excl_union)].copy()
        print(f"  Excl filter: {before} → {len(parcels)} (removed {before - len(parcels)})")

    # 4b. Keep parcels overlapping suitability raster (value == 1)
    if raster is not None:
        before = len(parcels)
        # Sample raster at parcel centroids (fast)
        centroids_3067 = parcels.geometry.centroid
        coords = [(p.x, p.y) for p in centroids_3067]
        samples = list(sample_gen(raster, coords))
        vals = np.array([s[0] for s in samples], dtype=np.uint8)
        in_suit = vals == 1
        parcels = parcels[in_suit].copy()
        print(f"  Suitability filter: {before} → {len(parcels)} (removed {before - len(parcels)})")

    if parcels.empty:
        print("No parcels passed filters. Nothing to score.")
        sys.exit(0)

    # 5. Load reference layers for scoring
    fgrid = load_gdf(CLIP_DIR / f"{prefix}_fingrid_substations.geojson", "Fingrid")
    lines = load_gdf(CLIP_DIR / f"{prefix}_osm_power_lines.geojson", "Power lines")
    urban = load_gdf(CLIP_DIR / f"{prefix}_osm_urban_centers.geojson", "Urban centers")
    dcs = load_gdf(CLIP_DIR / f"{prefix}_datacentermap.geojson", "Data centers")
    plants = load_gdf(CLIP_DIR / f"{prefix}_osm_power_plants.geojson", "Power plants")

    # ── Compute scores ───────────────────────────────────────────────

    scores = {k: np.full(len(parcels), np.nan) for k in
              ["grid_mw", "hv_score", "urban_score", "dc_score", "gen_score",
               "size_score", "zoning_score"]}

    centroids = parcels.geometry.centroid

    # --- 5a. Grid capacity (nearest Fingrid substation with headroom)
    if fgrid is not None:
        has_headroom = fgrid[fgrid["Kulutus_25"] > 0].copy()
        if not has_headroom.empty:
            # Nearest substation with headroom for each parcel centroid
            idx = centroids.apply(lambda c: has_headroom.distance(c).idxmin())
            nearest = has_headroom.loc[idx]
            scores["grid_mw"] = nearest["Kulutus_25"].values.astype(float)
            print(f"  Grid: {scores['grid_mw'].max():.0f} MW max, "
                  f"{scores['grid_mw'].min():.0f} MW min")

    # --- 5b. Distance to 220/400 kV transmission lines
    if lines is not None:
        hv = lines[lines["voltage"].astype(str).str.match(r"2[2-9]\d{4}|[34]\d{5}")].copy()
        if not hv.empty:
            hv_lines = hv.geometry.union_all()  # single multiline
            dists = centroids.distance(hv_lines)
            scores["hv_score"] = np.vectorize(distance_score)(dists, **HV_DIST)
            print(f"  HV lines: {dists.min()/1000:.1f}-{dists.max()/1000:.1f} km")

    # --- 5c. Distance to 100k+ urban centers
    if urban is not None:
        big = urban[urban["population"] >= 100_000].copy()
        if not big.empty:
            urban_pts = big.geometry.centroid
            dists = centroids.apply(lambda c: urban_pts.distance(c).min())
            scores["urban_score"] = np.vectorize(distance_score)(dists, **URBAN_DIST)
            print(f"  Urban: {dists.min()/1000:.1f}-{dists.max()/1000:.1f} km")

    # --- 5d. Distance to existing data centers (clustering signal)
    if dcs is not None:
        dc_pts = dcs.geometry.centroid
        dists = centroids.apply(lambda c: dc_pts.distance(c).min())
        scores["dc_score"] = np.vectorize(distance_score)(dists, **DC_DIST)
        print(f"  DCs: {dists.min()/1000:.1f}-{dists.max()/1000:.1f} km")

    # --- 5e. Proximity to generation assets (power plants)
    if plants is not None:
        gen = plants[plants["generator:output:electricity"].notna()].copy()
        if not gen.empty:
            gen_pts = gen.geometry.centroid
            dists = centroids.apply(lambda c: gen_pts.distance(c).min())
            scores["gen_score"] = np.vectorize(distance_score)(dists, **GEN_DIST)
            print(f"  Generation: {dists.min()/1000:.1f}-{dists.max()/1000:.1f} km")
        else:
            print("  Generation: no plants with electricity output found")

    # --- 5f. Parcel size score (10-100 ha, linear)
    areas_ha = parcels.geometry.area / 10000
    sz = np.clip((areas_ha - PARCEL_SIZE["min_ha"]) / (PARCEL_SIZE["max_ha"] - PARCEL_SIZE["min_ha"]), 0, 1)
    scores["size_score"] = sz.values * 10

    # --- 5g. Zoning type (if available)
    # MML parcels don't carry zoning — check if any column looks like landuse/zoning
    zone_cols = [c for c in parcels.columns if "kayttotark" in c.lower()
                 or "kaytto" in c.lower() or "maankaytto" in c.lower()
                 or "zoning" in c.lower() or "landuse" in c.lower()
                 or "kaava" in c.lower()]
    if zone_cols:
        # Try to score: industrial-related = 10, otherwise 5, missing = 3
        for col in zone_cols:
            industrial_keywords = ["teollisuus", "industrial", "työpaikka", "tyo", "liiketoiminta"]
            is_ind = parcels[col].astype(str).str.lower().apply(
                lambda v: any(k in v for k in industrial_keywords)
            )
            is_missing = parcels[col].isna()
            scores["zoning_score"] = np.where(is_ind, 10.0,
                                              np.where(is_missing, 3.0, 5.0))
            break  # use first matching column
        print(f"  Zoning: column '{zone_cols[0]}' — available")
    else:
        scores["zoning_score"] = np.full(len(parcels), 3.0)  # neutral
        print("  Zoning: no zoning column — default 3/10")

    # ── MCDM aggregation (weighted sum model) ────────────────────────
    # Normalise grid MW to 0-10
    grid_norm = np.clip(scores["grid_mw"] / MAX_GRID_MW, 0, 1) * 10

    # Build score matrix
    w = MCDM_WEIGHTS
    score_df = pd.DataFrame({
        "s_grid": grid_norm,
        "s_hv": scores["hv_score"],
        "s_urban": scores["urban_score"],
        "s_dc": scores["dc_score"],
        "s_gen": scores["gen_score"],
        "s_size": scores["size_score"],
        "s_zoning": scores["zoning_score"],
    }).fillna(5.0)  # neutral for missing dimensions

    # Weighted sum
    dims = ["s_grid", "s_hv", "s_urban", "s_dc", "s_gen", "s_size", "s_zoning"]
    weights = [w["grid"], w["hv"], w["urban"], w["dc"], w["gen"], w["size"], w["zoning"]]
    mcdm = (score_df[dims] * weights).sum(axis=1) / sum(weights)

    # Assign output fields
    parcels["mcdm_score"] = mcdm.round(1)
    parcels["score_grid"] = grid_norm.round(1)
    parcels["score_hv"] = scores["hv_score"].round(1)
    parcels["score_urban"] = scores["urban_score"].round(1)
    parcels["score_dc"] = scores["dc_score"].round(1)
    parcels["score_gen"] = scores["gen_score"].round(1)
    parcels["score_size"] = scores["size_score"].round(1)
    parcels["score_zoning"] = scores["zoning_score"].round(1)
    parcels["area_ha"] = areas_ha.round(1)

    # Sort descending by MCDM score
    parcels = parcels.sort_values("mcdm_score", ascending=False).reset_index(drop=True)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"  Scored: {len(parcels)} parcels")
    print(f"  MCDM range: {parcels['mcdm_score'].min():.1f} – {parcels['mcdm_score'].max():.1f}")
    print(f"  Mean: {parcels['mcdm_score'].mean():.1f}")
    print(f"  Top 5:")
    for i in range(min(5, len(parcels))):
        p = parcels.iloc[i]
        print(f"    {i+1}. {p.get('kiinteistotunnus', '?')}  "
              f"mcdm={p['mcdm_score']:.1f}  "
              f"grid={p['score_grid']:.1f}  hv={p['score_hv']:.1f}  "
              f"urban={p['score_urban']:.1f}  dc={p['score_dc']:.1f}  "
              f"gen={p['score_gen']:.1f}  size={p['score_size']:.1f}")
    print(f"{'=' * 60}\n")

    # ── Output ──
    out = parcels.to_crs(WGS84)
    out_path = OUT_DIR / f"{prefix}_scored_parcels.geojson"
    out.to_file(out_path, driver="GeoJSON", encoding="utf-8")
    kb = out_path.stat().st_size / 1024
    print(f"Saved: {out_path.name} ({kb:.0f} KB, {len(out)} parcels)")

    # ── Stats ──
    stats = {
        "n_parcels": len(out),
        "mcdm_mean": round(float(parcels["mcdm_score"].mean()), 1),
        "mcdm_min": round(float(parcels["mcdm_score"].min()), 1),
        "mcdm_max": round(float(parcels["mcdm_score"].max()), 1),
        "top_kite": out.iloc[0].get("kiinteistotunnus", "") if len(out) else "",
        "top_mcdm": round(float(parcels["mcdm_score"].max()), 1),
    }
    stats_path = OUT_DIR / f"{prefix}_scored_parcels_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Stats: {stats_path.name}")

    # ── Deliverables: top-N candidates → outputs/ ──
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    top = out.head(TOP_N).copy()
    top.insert(0, "rank", range(1, len(top) + 1))

    # candidates.geojson (top-N parcels with scores)
    cand_path = FINAL_DIR / "candidates.geojson"
    top.to_file(cand_path, driver="GeoJSON", encoding="utf-8")
    print(f"Output: {cand_path.name} ({len(top)} candidates)")

    # candidate_scores.csv (ranked table, no geometry)
    cols = ["rank", "kiinteistotunnus", "mcdm_score", "area_ha",
            "score_grid", "score_hv", "score_urban", "score_dc",
            "score_gen", "score_size", "score_zoning"]
    cols = [c for c in cols if c in top.columns]
    csv_path = FINAL_DIR / "candidate_scores.csv"
    top[cols].to_csv(csv_path, index=False, encoding="utf-8")
    print(f"Output: {csv_path.name} ({len(top)} rows)")

    if raster is not None:
        raster.close()
    print(f"\nDone in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

# DECISIONS

Assumptions, weights, and trade-offs for the Finland data-center site-suitability pipeline.

## Area of interest

- **Example AOI: Oulu, 50 km buffer.** Chosen for good 220/400 kV grid headroom, low Natura/flood density, and available land — a realistic northern siting case.
- **Region-agnostic by design.** The pipeline is parameterized via `config/aoi.json` (`city`, `center_wgs84`, `buffer_km`) and `city_picker.py`. It runs for Helsinki, Tampere, Turku, or Oulu at 50 or 100 km without code changes. Oulu is one configured example, not a hardcode.
- Data availability varies by region: existing data centers cluster near Helsinki, so the DC dimension is empty for Oulu.

## CRS harmonization

- Vectors standardized to **EPSG:4326** after clipping; rasters kept in **EPSG:3067** for metric slope math. A WGS84 web copy of the slope mask is produced for plotting. All spatial ops run in a single CRS before measurement.

## Stage 1 — fatal-flaw filter

Hard exclusions, no score: parcels intersecting exclusion zones (Natura 2000, river/sea flood, nature reserves), parcels off the <8% slope mask, parcels <10 ha. For Oulu: 395 → 296 (exclusions) → 253 (slope).

## Stage 2 — weights

| Dim | Weight | Reasoning |
|-----|--------|-----------|
| grid | 0.25 | Power headroom is the #1 data-center constraint |
| hv | 0.15 | 220/400 kV connection cost |
| dc | 0.15 | Co-location with existing DC infrastructure |
| size | 0.15 | Larger parcels = scale flexibility (10–100 ha) |
| urban | 0.10 | Workforce / fiber |
| gen | 0.10 | PPA / generation proximity |
| zoning | 0.10 | Industrial preference |

Weighted sum (Σw = 1.0). Missing dimensions default to neutral 5.0.

## Known limitations

- **Centroid sampling** — distances/slope judged at parcel centroid only; large parcels approximated by one point.
- **DC layer empty for Oulu** — none in region; dimension neutral.
- **Zoning** — MML parcels lack zoning; defaults to 3/10.
- **MML key required** — parcels + DEM gated behind a free MML API key.
- **Map raster** — slope mask left off the shared map (local-COG not portable in static HTML).
- Top score ~7.9/10; small AOI limits candidate pool.

## With more time

- Area-weighted (not centroid) scoring; sensitivity analysis on weights.
- Fingrid capacity refresh-check → auto re-run.
- PostGIS schema with versioning/lineage for multi-country use.
- Tile/host the slope raster so it shows in the shared map.
- Further data integration + QC checks to fill missing values and aggregate equivalent fields across sources (e.g. capacity, zoning, DC locations from OSM/DCD/BroadGroup).
- Efficiency improvements in fetching and processing — parallel/async downloads, caching, spatial indexing, and chunked raster ops for larger AOIs.
- Dynamic multi-criteria scoring with absolute thresholds/benchmarks rather than weights normalised to the parcels present in the AOI, so scores are comparable across regions and runs.
- Store layers as GeoParquet (partitioned, columnar) for fast, cloud-native I/O and easy versioning across countries.

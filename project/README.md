# GIS Site Suitability — Finland Data Centers

Reproducible geospatial pipeline for data-center site selection in Finland. It ingests 9 layers, harmonizes CRS, clips to an area of interest, applies a two-stage suitability model (hard exclusions + weighted scoring), and produces a ranked shortlist plus an interactive map.

**Region-agnostic:** Oulu is shown as the example AOI, but the pipeline works for any major Finnish city (Helsinki, Tampere, Turku, Oulu) at a 50 or 100 km buffer — set it in `config/aoi.json` or pick interactively with `city_picker.py`. Data availability varies by region (e.g. no existing data centers near Oulu).

## Structure

```
project/
├── config/
│   ├── aoi.json           # AOI center + buffer radius
│   ├── keys.json          # API keys (MML — fill in before fetch)
│   └── config.py          # Shared config loader
├── templates/
│   └── city_picker.html   # Leaflet city selector
├── data/
│   ├── raw/               # Fetched layers
│   └── etl/               # Processed data (clipped, suitability, exclusions)
├── scripts/
│   ├── city_picker.py     # Interactive server → auto-fetch
│   ├── fetch_all.py         # Fetch orchestrator
│   ├── run_etl.py         # ETL orchestrator
│   ├── visualize_map.py   # Interactive map
│   └── fetching/
│       ├── fetch_fingrid.py       # Fingrid grid capacity
│       ├── fetch_osm.py           # OSM power lines/substations/plants/DCs
│       ├── fetch_urban_centers.py # Cities ≥100k
│       ├── fetch_natura2000.py    # Natura 2000 sites
│       ├── fetch_flood_zones.py   # River + sea flood zones
│       ├── fetch_nature_reserves.py # State/private reserves
│       ├── fetch_land_parcels.py  # MML parcels (needs API key)
│       ├── fetch_dem.py           # MML 2m DEM (needs API key)
│       └── fetch_datacentermap.py # Data Center Map scraper
│   └── etl/
│       ├── fetch_finland_boundary.py # Finland boundary (OSM)
│       ├── clip_to_aoi.py            # Clip all data to AOI
│       ├── process_dem_tiles.py      # Slope <8% mask + WGS84 web copy
│       ├── merge_exclusions.py       # Merge exclusion zones
│       └── qc_report.py              # Validation report
│   └── scoring/
│       └── score_parcels.py # Two-stage suitability model
├── outputs/
│   ├── candidates.geojson   # Top-20 candidate parcels (scored)
│   ├── candidate_scores.csv # Ranked score table
│   └── final_map.html       # Final deliverable map
└── .gitignore
```

## Quick start

### 1. API key

Get a free MML key at [omatili.maanmittauslaitos.fi](https://omatili.maanmittauslaitos.fi) and save:

```bash
echo '{"MML_KEY": "your-key-here"}' > config/keys.json
```

### Run with Docker (recommended)

No system GDAL needed — wheels bundle it. From the repo root:

```bash
docker build -t geotask:latest .                          # core pipeline
docker build --build-arg WITH_PLAYWRIGHT=1 -t geotask .   # + data-center scraper

# fetch → ETL + scoring → map (outputs land in project/outputs/)
MML_KEY=your-key docker compose run --rm pipeline python scripts/fetch_all.py
docker compose up
```

`data/`, `outputs/`, `config/` are volume-mounted, so results persist on the host.

### Run manually

```bash
pip install -r requirements.txt
playwright install chromium      # only for fetch_datacentermap.py
python scripts/fetch_all.py      # fetch layers
python scripts/run_etl.py        # clip, slope, exclusions, QC, scoring
python scripts/visualize_map.py  # interactive map
```

Scoring runs as the last ETL step and writes the deliverables to `outputs/`. The map writes to both `data/etl/<City>_FINLAND_map.html` and `outputs/final_map.html`.

## Choosing the AOI

Edit `config/aoi.json` (`city`, `center_wgs84`, `buffer_km`) or run `python scripts/city_picker.py` and click a city; saving sets the AOI and triggers fetching. All filenames are prefixed `<City>_FINLAND_*`, so switching city + buffer re-runs cleanly end to end.

## Data sources

| Layer | Source |
|-------|--------|
| Grid capacity | Fingrid ArcGIS FeatureServer |
| Power network | OSM Overpass API |
| Urban centers | OSM |
| Natura 2000 | EEA ArcGIS REST |
| Flood zones | SYKE WFS |
| Nature reserves | SYKE WFS |
| Land parcels | MML OGC API Features (key) |
| DEM 2m | MML OGC API Processes (key) |
| Data centers | datacentermap.com |

## Pipeline

1. **Fetch** — downloads each layer to `data/raw/` as GeoJSON
2. **Finland boundary** — from OSM relation 54224
3. **Clip** — clip to AOI circular buffer + Finland boundary, reproject to EPSG:4326
4. **Gradient** — slope <8% binary mask raster (EPSG:3067) + WGS84 web copy
5. **Exclusions** — merge Natura2000 + flood + reserves into one layer
6. **QC report** — validates CRS, geometry, feature counts
7. **Scoring** — two-stage suitability → top-20 candidates
8. **Map** — interactive GeoLibre map: candidates, grid, exclusions, legend + colorbar

All outputs in EPSG:4326 (GeoJSON) / EPSG:3067 (TIFF).

## Scoring model

**Stage 1 — fatal-flaw filter:** drop parcels in exclusion zones (Natura/flood/reserves), off the <8% slope mask, or <10 ha.

**Stage 2 — weighted scoring** (7 dims, each 0–10, centroid-based):

| Dim | Weight | Signal |
|-----|--------|--------|
| grid | 0.25 | MW headroom at nearest Fingrid substation |
| hv | 0.15 | distance to 220/400 kV lines |
| dc | 0.15 | distance to existing data centers |
| size | 0.15 | parcel area (10–100 ha) |
| urban | 0.10 | distance to 100k+ city |
| gen | 0.10 | distance to power plants |
| zoning | 0.10 | industrial land use |

Weighted sum (Σw = 1.0). Missing dims default to neutral 5.0. Ranked top-20 → `outputs/`.

## Dependencies

Core deps are pinned in [requirements.txt](requirements.txt): geopandas, rasterio, shapely, pyproj, requests, scipy, numpy, pandas, geolibre. Playwright (+ Chromium) is optional and only needed for the data-center scraper.

```bash
pip install -r requirements.txt
playwright install chromium   # optional
```

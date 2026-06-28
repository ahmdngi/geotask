# GIS Site Suitability — Finland Data Centers

Geospatial data pipeline for data center siting analysis in Finland. Downloads and processes 9 data layers, computes slope gradient, clips to AOI, and produces an interactive map.

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
│       ├── compute_gradient.py       # Slope <8% mask
│       ├── merge_exclusions.py       # Merge exclusion zones
│       └── qc_report.py              # Validation report
├── outputs/
│   ├── candidates.geojson   # Candidate parcels (placeholder — scoring TBD)
│   ├── candidate_scores.csv # Ranked scores (placeholder — scoring TBD)
│   └── final_map.html       # Final deliverable map
└── .gitignore
```

## Quick start

### 1. API key

Get a free MML key at [omatili.maanmittauslaitos.fi](https://omatili.maanmittauslaitos.fi) and save:

```bash
echo '{"MML_KEY": "your-key-here"}' > config/keys.json
```

### 2. Fetch data

```bash
# Pick a city interactively — runs all fetch scripts on save:
python scripts/city_picker.py

# Or manually:
python scripts/fetch_all.py
```

### 3. Run ETL

```bash
python scripts/run_etl.py
```

### 4. View map

```bash
python scripts/visualize_map.py
```

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
3. **Clip** — clip to AOI circular buffer + Finland boundary
4. **Gradient** — slope <8% binary mask raster + coverage outline
5. **Exclusions** — merge Natura2000 + flood + reserves into one layer
6. **QC report** — validates CRS, geometry, feature counts
7. **Map** — interactive Leaflet map with all layers + slope overlay

All outputs in EPSG:4326 (GeoJSON) / EPSG:3067 (TIFF).

## Dependencies

```
geopandas pyproj shapely requests rasterio scipy numpy geolibre playwright
```

Install:

```bash
pip install geopandas pyproj shapely requests rasterio scipy numpy geolibre
playwright install chromium
```

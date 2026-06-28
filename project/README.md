# KRIOS GIS Assignment Project

Geospatial site suitability analysis for data center siting in Finland.

## Structure

```
project/
├── config/
│   ├── aoi.json              # AOI city + bbox (set via city picker or manually)
│   └── keys.json             # API keys template (fill in before MML scripts)
├── templates/
│   └── city_picker.html      # Leaflet interactive city selector (12 Finnish cities)
├── data/
│   └── raw/                  # All fetched layers land here
├── scripts/
│   ├── config.py             # Shared config loader (reads aoi.json + keys.json)
│   ├── city_picker.py        # Starts local HTTP server → Leaflet city picker
│   ├── run_all.py            # Orchestrator — runs fetch scripts in order
│   ├── fetch_fingrid.py      # Fingrid grid substation capacity
│   ├── fetch_osm.py          # OSM power lines, substations, plants, data centers
│   ├── fetch_urban_centers.py # Cities/towns with population >= 100k
│   ├── fetch_natura2000.py   # Natura 2000 protected sites
│   ├── fetch_flood_zones.py  # River + sea flood hazard zones (SYKE WFS)
│   ├── fetch_nature_reserves.py # State/private nature reserves (SYKE WFS)
│   ├── fetch_land_parcels.py # MML land parcels (kiinteistöt — needs API key)
│   └── fetch_dem.py          # MML 2m digital elevation model (needs API key)
├── notebooks/
│   └── 01_exploration.ipynb  # Exploration notebook
├── outputs/                  # Final deliverables
├── decisions/                # Assumptions, limitations, decision log
└── .gitignore                # Ignores data/, keys.json, __pycache__
```

## Workflow

### 1. Set API keys

Get a free MML key at [omatili.maanmittauslaitos.fi](https://omatili.maanmittauslaitos.fi) and save it:

```bash
echo '{"MML_KEY": "your-key-here"}' > config/keys.json
```

### 2. Pick a city

Two ways:

```bash
# Interactive Leaflet map — click a city, hit "Save & Close":
python scripts/city_picker.py
# Opens http://127.0.0.1:8765 — 12 Finnish cities to choose from

# Or edit config/aoi.json directly:
# {"city": "Tampere", "bbox_wgs84": [60.9978, 23.2616, 61.9978, 24.2616]}
```

### 3. Fetch data

```bash
# Fetch everything:
python scripts/run_all.py

# Select specific layers:
python scripts/run_all.py --only fingrid osm natura2000

# Skip slow ones (DEM, land parcels):
python scripts/run_all.py --skip dem land_parcels
```

### 4. Output naming

All layers land in `data/raw/` as:
```
{City}_FINLAND_{layer}.geojson
```
Example: `Helsinki_FINLAND_fingrid_substations.geojson`

All outputs are reprojected to **EPSG:3067** (Finnish TM35fin national standard).

## Data Sources

| Layer | Source | Auth | CRS |
|-------|--------|------|-----|
| Grid capacity | Fingrid ArcGIS FeatureServer | None | EPSG:3067 native |
| Power network | OSM Overpass API | User-Agent | WGS84 → EPSG:3067 |
| Urban centers | OSM Overpass API | User-Agent | WGS84 → EPSG:3067 |
| Natura 2000 | EEA ArcGIS REST | None | WGS84 → EPSG:3067 |
| Flood zones | SYKE WFS | None | WGS84 → EPSG:3067 |
| Nature reserves | SYKE WFS | None | WGS84 → EPSG:3067 |
| Land parcels | MML OGC API Features | MML_KEY | EPSG:3067 native |
| DEM 2m | MML OGC API Processes | MML_KEY | EPSG:3067 native |

## Exclusion Zones (No Filtering)

Natura 2000, flood zones, and nature reserves are fetched as-is — all features intersecting the AOI bbox are saved without filtering. Filtering happens in the scoring stage.

## Dependencies

```
geopandas pyproj shapely pandas requests rasterio
```

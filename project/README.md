# KRIOS GIS Assignment Project

This folder contains the project scaffold for the geospatial technical assignment.

## Structure
- notebooks: exploratory notebook(s)
- scripts: pipeline scripts
- data: raw/processed/output data staging
- outputs: final deliverable artifacts
- decisions: assumptions, limitations, and decision log
- docker: container-related files

## Status

- **Notebook** `notebooks/01_exploration.ipynb` — validates Fingrid substation connection capacity layer (`Kytkinlaitokset_Fingrid` → `Sähköasemat_liityntäkapasiteetti`).
- **Chunks**:
  - 1: List ArcGIS services
  - 2: Fingrid substations (172 features, `Kulutus_25` field)
  - 3: OSM extraction (power lines 110-400 kV, substations, power plants/generators, data centers) via Overpass API with 429 retry logic
  - 4: Combined GeoLibre map (Fingrid + OSM layers)
- **Data** `data/processed/` — Fingrid substations (172) + OSM layers: power lines (422), substations (858), power plants, data centers.

## Next Step
Implement the scripts in execution order: fetch_data.py, ingest.py, etl.py, score_sites.py, generate_map.py.

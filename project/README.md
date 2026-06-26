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

- **Notebook** `notebooks/01_exploration.ipynb` — validates Fingrid substation connection capacity layer (`Kytkinlaitokset_Fingrid` → `Sähköasemat_liityntäkapasiteetti`). Chunk 3 visualises all 172 features via GeoLibre.
- **Data** `data/processed/fingrid_substations.geojson` — cached output from the notebook (172 substations, EPSG:4326, consumption MW per site).

## Next Step
Implement the scripts in execution order: fetch_data.py, ingest.py, etl.py, score_sites.py, generate_map.py.

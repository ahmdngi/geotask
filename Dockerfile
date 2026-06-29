# Finland data-center site-suitability pipeline
# python:3.11-slim is enough — geopandas/rasterio/shapely/pyproj ship manylinux
# wheels that bundle GDAL/PROJ/GEOS, so no system GDAL install is required.
FROM python:3.11-slim

# Optional: install Playwright + Chromium for fetch_datacentermap.py
ARG WITH_PLAYWRIGHT=0

WORKDIR /app

# Minimal runtime libs the rasterio/pyogrio wheels need (GDAL is bundled in wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libexpat1 && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY project/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$WITH_PLAYWRIGHT" = "1" ]; then \
        pip install --no-cache-dir playwright && \
        playwright install --with-deps chromium; \
    fi

# App
COPY project/ /app/

ENV PYTHONUNBUFFERED=1

# Default: run the full ETL + scoring pipeline.
# Override, e.g.: docker run img python scripts/fetch_all.py
CMD ["python", "scripts/run_etl.py"]

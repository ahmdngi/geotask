# BONUS

Optional extensions. Sketches, not implemented.

## 1. Fingrid capacity refresh check

**Goal:** detect when the Fingrid "Sähkön kulutuskapasiteetti" layer updates and trigger a re-run.

**Detection (cheapest first):**
- Poll the ArcGIS FeatureServer metadata daily and compare `editingInfo.lastEditDate` (or layer `serviceItemId` modified time) against the value stored from the last run. If it changed, the layer was updated.
- Fallbacks: HTTP `ETag`/`Last-Modified` on the export; or a content hash of the fetched features (geometry + capacity fields). Hash differs → changed.

**Trigger:**
- Scheduled job (cron / GitHub Actions / Airflow) → check metadata → on change, run `fetch_fingrid.py`, then re-run ETL + scoring + map for affected AOIs only.
- Store last-seen timestamp/hash in a small state file or a `dataset_versions` table; emit a notification on change.

```
schedule → check lastEditDate vs stored → changed? → fetch → ETL → score → map → notify
```

## 2. PostGIS schema (multi-country, versioning + lineage)

Layers stored as versioned tables, partitioned by country, with a snapshot per fetch.

```sql
-- Each ingest = one snapshot, immutable
CREATE TABLE source_snapshot (
  snapshot_id   BIGSERIAL PRIMARY KEY,
  layer         TEXT,            -- fingrid, osm_lines, natura, flood, parcels...
  country       TEXT,            -- FI, SE, NO...
  fetched_at    TIMESTAMPTZ,
  source_url    TEXT,
  source_hash   TEXT,            -- dedup / change detection
  crs           INT
);

-- One table per layer, all snapshots kept; valid_from/valid_to for current view
CREATE TABLE substations (
  id            BIGSERIAL PRIMARY KEY,
  snapshot_id   BIGINT REFERENCES source_snapshot,
  country       TEXT,
  capacity_mw   NUMERIC,
  attrs         JSONB,           -- raw source fields (lineage)
  geom          GEOMETRY(Point, 3067),
  valid_from    TIMESTAMPTZ,
  valid_to      TIMESTAMPTZ      -- NULL = current
);
CREATE INDEX ON substations USING GIST (geom);
```

- **Versioning:** never overwrite; new snapshot per fetch, close prior rows (`valid_to`). Query current with `valid_to IS NULL`; query history by date.
- **Lineage:** `snapshot_id` → `source_snapshot` ties every feature to URL, hash, fetch time. Raw fields kept in `attrs`.
- **Multi-country:** `country` column + partitioning; all geoms in metric national CRS (3067 for FI) or a common projection.
- Candidates/scores reference the snapshot used, so results are reproducible.
- **Storage:** persist each snapshot as partitioned **GeoParquet** (by country/layer/fetch date) for cloud-native, columnar reads; load to PostGIS for spatial queries. Parquet = versioned lineage on object storage, PostGIS = serving.

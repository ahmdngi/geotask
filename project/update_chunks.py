import json

path = "/root/geotask/project/notebooks/01_exploration.ipynb"
with open(path) as f:
    nb = json.load(f)

# Chunk 3 (index 6): Replace OSM_BBOX
c3 = nb["cells"][6]
new_src = []
for line in c3["source"]:
    if 'OSM_BBOX = "' in line:
        new_src.append('# Uses AOI_BBOX_WGS84 from Chunk 0\n')
        continue
    new_src.append(line)
c3["source"] = new_src
for i, line in enumerate(c3["source"]):
    if "{OSM_BBOX}" in line:
        c3["source"][i] = line.replace("{OSM_BBOX}", "{AOI_BBOX_WGS84}")

# Chunk 3b (index 7)
c3b = nb["cells"][7]
new_src = []
for line in c3b["source"]:
    if 'bbox_finland = "' in line:
        new_src.append('# Uses AOI_BBOX_WGS84 from Chunk 0\n')
        continue
    if "{bbox_finland}" in line:
        new_src.append(line.replace("{bbox_finland}", "{AOI_BBOX_WGS84}"))
        continue
    if "is_in:country" in line or "addr:country" in line:
        continue
    if "country and country.lower() not in" in line:
        continue
    new_src.append(line)
c3b["source"] = new_src

# Chunk 3c (index 8): Replace SEARCH_BBOXES with AOI_BBOX_3067
c3c = nb["cells"][8]
new_src = []
skip = False
for line in c3c["source"]:
    if "SEARCH_BBOXES = [" in line:
        skip = True
        new_src.append("# Use the full AOI bbox from Chunk 0\n")
        new_src.append("all_large = []\n")
        new_src.append("seen_ids = set()\n")
        new_src.append("url = (\n")
        new_src.append('    f"{BASE}/collections/PalstanSijaintitiedot/items"\n')
        new_src.append('    f"?bbox={AOI_BBOX_3067}"\n')
        new_src.append('    "&bbox-crs=http://www.opengis.net/def/crs/EPSG/0/3067"\n')
        new_src.append('    "&crs=http://www.opengis.net/def/crs/EPSG/0/3067"\n')
        new_src.append('    "&limit=1000"\n')
        new_src.append(")\n")
        new_src.append("count = 0\n")
        new_src.append("while url and count < 10000:\n")
        continue
    if skip:
        if "for bbox in SEARCH_BBOXES" in line:
            skip = False
            continue
        if line.strip().startswith('"') or line.strip().startswith("'"):
            continue
        if "all_large = []" in line or "seen_ids = set()" in line:
            continue
        if line.strip() == "" or line.strip().endswith(","):
            continue
        skip = False
    new_src.append(line)
c3c["source"] = new_src

# Chunk 3d (index 9): Replace BBOX_DEM with AOI buffer with truncation
c3d = nb["cells"][9]
new_src = []
for line in c3d["source"]:
    if "BBOX_DEM = " in line and "384000" in line:
        new_src.append("# Use AOI bbox from Chunk 0, truncate to MML 100km2 limit\n")
        new_src.append("BBOX_DEM = AOI_BBOX_3067_LIST\n")
        new_src.append("dem_area_km2 = (BBOX_DEM[2]-BBOX_DEM[0])*(BBOX_DEM[3]-BBOX_DEM[1])/1e6\n")
        new_src.append("if dem_area_km2 > 90:\n")
        new_src.append("    cx = (BBOX_DEM[0] + BBOX_DEM[2]) / 2\n")
        new_src.append("    cy = (BBOX_DEM[1] + BBOX_DEM[3]) / 2\n")
        new_src.append("    half = (90e6 ** 0.5) / 2\n")
        new_src.append("    BBOX_DEM = [cx-half, cy-half, cx+half, cy+half]\n")
        new_src.append("    print(f'DEM bbox truncated to ~{dem_area_km2:.0f} km2')\n")
        continue
    new_src.append(line)
c3d["source"] = new_src

# Chunk 3e (index 10): Replace bbox vars
c3e = nb["cells"][10]
for i, line in enumerate(c3e["source"]):
    if 'BBOX_3067 = "300000' in line:
        c3e["source"][i] = "BBOX_3067 = AOI_BBOX_3067_FULL  # from Chunk 0\n"
    if 'BBOX_4326 = "19,59.5' in line:
        c3e["source"][i] = "BBOX_4326 = AOI_BBOX_WGS84  # from Chunk 0\n"

# Chunk 4 (index 11): Update map center
c4 = nb["cells"][11]
for i, line in enumerate(c4["source"]):
    if "center=[25.0, 60.2]" in line:
        c4["source"][i] = "    center=[AOI_CENTER_WGS84[1], AOI_CENTER_WGS84[0]],  # lon,lat\n"

# Update workflow
nb["cells"][1]["source"] = [
    "## Workflow\n",
    "\n",
    "0. **Chunk 0** -- Set AOI city and 100km buffer. Change CITY to switch.\n",
    "1. **Chunk 1** -- List ArcGIS services.\n",
    "2. **Chunk 2** -- Inspect Fingrid layer schema.\n",
    "3. **Chunk 2b** -- Download Fingrid substations -> ./data/fingrid_substations.geojson.\n",
    "4. **Chunk 3** -- OSM layers (power lines, substations, plants, DCs).\n",
    "5. **Chunk 3b** -- Urban centers (>=100k) from OSM.\n",
    "6. **Chunk 3c** -- Land parcels >=10ha from MML. Needs MML_KEY.\n",
    "7. **Chunk 3d** -- DEM + gradient <8%. Needs MML_KEY + GDAL.\n",
    "8. **Chunk 3e** -- Exclusion zones (Natura 2000, flood, reserves) from EEA + SYKE.\n",
    "9. **Chunk 4** -- Combined GeoLibre map all 8 layers.\n",
]

with open(path, "w") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print("All chunks updated")

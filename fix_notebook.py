import json

with open('project/notebooks/01_exploration.ipynb') as f:
    nb = json.load(f)

src = nb['cells'][9]['source']

# Fix 1: The print bug — recalculate area after truncation
fix1_old = "    print(f'DEM bbox truncated to ~{dem_area_km2:.0f} km2')\\n"
fix1_new = "    new_area = (BBOX_DEM[2]-BBOX_DEM[0])*(BBOX_DEM[3]-BBOX_DEM[1])/1e6\\n    print(f'DEM bbox truncated to ~{new_area:.0f} km2')\\n"
for i, l in enumerate(src):
    if l == fix1_old:
        src[i] = fix1_new
        break

# Fix 2: Replace xarray-spatial + rioxarray with scipy sobel (no numba issues)
step4_idx = next(i for i, l in enumerate(src) if 'Compute slope' in l)
step5_end = next(i for i, l in enumerate(src) if 'Done. Suitable' in l)

new_step4_5 = [
    '# Step 4: Compute slope via Sobel gradient (no numba/gdal)\\n',
    'import rasterio\\n',
    'from scipy.ndimage import sobel\\n',
    '\\n',
    'slope_path = OUT / "gradient_percent.tiff"\\n',
    'with rasterio.open(dem_path) as src:\\n',
    '    dem = src.read(1).astype(np.float64)\\n',
    '    dx = sobel(dem, axis=1) / src.res[0]\\n',
    '    dy = sobel(dem, axis=0) / src.res[1]\\n',
    '    slope_deg = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)\\n',
    '    slope_pct = np.tan(np.deg2rad(slope_deg)) * 100\\n',
    '    slope_pct = np.where(np.isfinite(slope_pct), slope_pct, 10000.0)\\n',
    '\\n',
    'with rasterio.open(\\n',
    '    slope_path, "w", driver="GTiff",\\n',
    '    height=slope_pct.shape[0], width=slope_pct.shape[1],\\n',
    '    count=1, dtype=np.float32,\\n',
    '    crs=src.crs, transform=src.transform,\\n',
    ') as dst:\\n',
    '    dst.write(slope_pct.astype(np.float32), 1)\\n',
    'print(f"Slope raster (percent): {slope_path}")\\n',
    '\\n',
    '# Step 5: Reclassify to binary\\n',
    'suitable_path = OUT / "gradient_suitable_8pct.tiff"\\n',
    'suitable = (slope_pct < 8).astype(np.uint8)\\n',
    'with rasterio.open(\\n',
    '    suitable_path, "w", driver="GTiff",\\n',
    '    height=suitable.shape[0], width=suitable.shape[1],\\n',
    '    count=1, dtype=np.uint8,\\n',
    '    crs=src.crs, transform=src.transform,\\n',
    '    nodata=0,\\n',
    ') as dst:\\n',
    '    dst.write(suitable, 1)\\n',
    'print(f"Suitable gradient mask: {suitable_path}")\\n',
    'print("Done. Suitable areas = 1 (slope < 8%), Unsuitable = 0 (slope >= 8%)")\\n',
]

# Remove the old xarray-specific imports (keep numpy)
src = [l for l in src if 'from xrspatial import slope' not in l]
src = [l for l in src if 'import rioxarray' not in l]
src = [l for l in src if 'import xarray as xr' not in l]

# Replace step 4-5 section
nb['cells'][9]['source'] = src[:step4_idx] + new_step4_5

with open('project/notebooks/01_exploration.ipynb', 'w') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print("Fixed both bugs")

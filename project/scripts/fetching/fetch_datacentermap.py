"""
Fetch data center locations from Data Center Map (Finland).

Source: datacentermap.com (scraped via Playwright for JS-rendered content)
Native CRS: WGS84 (EPSG:4326)
Output: data/raw/{CITY}_FINLAND_datacentermap.geojson (EPSG:3067)

Uses Playwright to bypass the Vercel JS challenge.
Data comes from Next.js page props as embedded GeoJSON.
"""

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.config import AOI_BBOX_WGS84, AOI_CITY

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
TARGET_CRS = "EPSG:3067"
BASE_URL = "https://www.datacentermap.com"


def extract_nextjs_props(page) -> dict | None:
    """Extract pageProps from Next.js JSON blob in script tags."""
    for s in page.query_selector_all("script"):
        t = s.inner_text()
        if "mapdata" not in t:
            continue
        idx = t.find('{"props"')
        if idx < 0:
            continue
        blob = t[idx:]
        depth = 0
        for i, c in enumerate(blob):
            if c == "{":
                depth += 1
            if c == "}":
                depth -= 1
            if depth == 0:
                try:
                    data = json.loads(blob[: i + 1])
                    return data.get("props", {}).get("pageProps", {})
                except json.JSONDecodeError:
                    return None
    return None


def point_in_bbox(lon, lat) -> bool:
    """Check if a point falls within the AOI bounding box."""
    min_lat, min_lon, max_lat, max_lon = [float(v) for v in AOI_BBOX_WGS84]
    return min_lat <= float(lat) <= max_lat and min_lon <= float(lon) <= max_lon


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Data Center Map — Finland data center scraper")
    print(f"  AOI: {AOI_BBOX_WGS84} ({AOI_CITY})")
    print(f"  Output: {DATA_DIR / f'{AOI_CITY}_FINLAND_datacentermap.geojson'}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Step 1: Get all Finnish cities from country page
        print("\nStep 1: Fetching city list...")
        try:
            page.goto(f"{BASE_URL}/finland/", timeout=30000)
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  ERROR loading Finland page: {e}")
            browser.close()
            sys.exit(1)

        props = extract_nextjs_props(page)
        if not props:
            print("  ERROR: Could not extract page props")
            browser.close()
            sys.exit(1)

        all_cities = props.get("mapdata", {}).get("geos", [])
        print(f"  Finland has {len(all_cities)} cities with DCs")

        # Filter cities by AOI
        target_cities = []
        for c in all_cities:
            coords = c.get("geometry", {}).get("coordinates", [])
            if len(coords) >= 2:
                if point_in_bbox(coords[0], coords[1]):
                    target_cities.append(c)

        print(f"  {len(target_cities)} cities intersect AOI")
        if not target_cities:
            print("  No cities within AOI — trying cities near AOI boundary anyway")
            target_cities = all_cities[:3]  # fallback: try a few nearby

        # Step 2: Visit each city that intersects AOI
        print(f"\nStep 2: Scraping data centers...")
        all_dcs = []

        for city_feature in target_cities:
            cp = city_feature.get("properties", {})
            city_slug = cp.get("link", "")
            city_name = cp.get("name", city_slug)
            dc_count = cp.get("datacenters", 0)

            if not city_slug or dc_count == 0:
                continue

            print(f"  {city_name} ({dc_count} DCs)...", end=" ", flush=True)

            try:
                page.goto(f"{BASE_URL}/finland/{city_slug}/", timeout=20000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f"SKIP (timeout)")
                continue

            city_props = extract_nextjs_props(page)
            if not city_props:
                print("SKIP (no data)")
                continue

            dcs = city_props.get("mapdata", {}).get("dcs", [])
            stats = city_props.get("geodata", {}).get("meta_stats", {}).get("dcs", {})

            # Enrich each DC with city and market stats
            for dc in dcs:
                dc["properties"]["city"] = city_name
                dc["properties"]["city_slug"] = city_slug
                for k, v in stats.items():
                    dc["properties"][f"market_{k}"] = v

            # Filter to AOI
            before = len(dcs)
            dcs_filtered = [dc for dc in dcs if point_in_bbox(
                dc["geometry"]["coordinates"][0],
                dc["geometry"]["coordinates"][1]
            )]
            print(f"{len(dcs_filtered)}/{before} in AOI")

            all_dcs.extend(dcs_filtered)

        browser.close()

    # Step 3: Save
    print(f"\nStep 3: Saving...")
    if not all_dcs:
        print("  No data centers found within AOI — skipping save.")
        return

    import geopandas as gpd

    fc = {"type": "FeatureCollection", "features": all_dcs}
    gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
    gdf = gdf.to_crs(TARGET_CRS)

    out_path = DATA_DIR / f"{AOI_CITY}_FINLAND_datacentermap.geojson"
    gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")

    print(f"  Saved:  {out_path.name}")
    print(f"  CRS:    {TARGET_CRS}")
    print(f"  Size:   {len(gdf)} features")

    if "companyname" in gdf.columns:
        companies = gdf["companyname"].unique()
        print(f"  Operators: {len(companies)}")
        for c in sorted(companies):
            count = len(gdf[gdf["companyname"] == c])
            print(f"    {c}: {count}")


if __name__ == "__main__":
    main()

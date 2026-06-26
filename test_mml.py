"""Test MML parcels + DEM for Helsinki core area"""
import requests, json, time
from shapely.geometry import shape
from pathlib import Path

API_KEY = "32be99cf-6b41-44bf-9810-434a9a31265b"

# === PARCELS ===
BASE = "https://avoin-paikkatieto.maanmittauslaitos.fi/kiinteisto-avoin/simple-features/v3"
BBOX = "384000,6669000,387000,6672000"

print("=== PARCELS ===")
r = requests.head(
    f"{BASE}/collections/PalstanSijaintitiedot/items",
    params={"bbox": BBOX, "bbox-crs": "http://www.opengis.net/def/crs/EPSG/0/3067", "limit": 1},
    auth=(API_KEY, ""), timeout=30
)
total = int(r.headers.get("OGC-NumberMatched", 0))
print(f"Total in test area: {total}")

all_features = []
offset = 0
while offset < 5000:
    r = requests.get(
        f"{BASE}/collections/PalstanSijaintitiedot/items",
        params={"bbox": BBOX, "bbox-crs": "http://www.opengis.net/def/crs/EPSG/0/3067",
                "limit": 1000, "offset": offset},
        auth=(API_KEY, ""), timeout=60
    )
    if r.status_code != 200:
        break
    feats = r.json().get("features", [])
    if not feats:
        break
    all_features.extend(feats)
    offset += len(feats)
    print(f"  {len(all_features)} / {total}")
    time.sleep(0.3)

print(f"Fetched: {len(all_features)}")

large = []
for f in all_features:
    g = f["geometry"]
    if g and g["type"] == "Polygon":
        try:
            s = shape(g)
            ha = s.area / 10000
            if ha >= 10:
                large.append({
                    "type": "Feature", "geometry": g,
                    "properties": {"id": f["properties"]["kiinteistotunnus"], "area_ha": round(ha, 1)}
                })
        except:
            pass

fc = {"type": "FeatureCollection", "features": large}
Path("notebooks/data/land_parcels.geojson").write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
print(f"Parcels >=10ha: {len(large)}. Saved.")
for p in large[:5]:
    print(f"  {p['properties']['id']}: {p['properties']['area_ha']} ha")

print("\n=== DEM ===")
PROC = "https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1"
job = {"processId": "korkeusmalli_2m_bbox", "parameters": {
    "bbox": BBOX, "crs": "http://www.opengis.net/def/crs/EPSG/0/3067", "format": "image/tiff"
}}
r = requests.post(f"{PROC}/jobs", json=job, auth=(API_KEY, ""), timeout=30)
print(f"DEM job: {r.status_code}")
if r.status_code in (200, 201):
    jid = r.json().get("jobId", "")
    print(f"Job: {jid}")
    for i in range(10):
        time.sleep(3)
        r2 = requests.get(f"{PROC}/jobs/{jid}", auth=(API_KEY, ""), timeout=30)
        s = r2.json().get("status", "")
        print(f"  Poll {i+1}: {s}")
        if s in ("successful", "finished"):
            res = r2.json().get("result", {})
            if isinstance(res, dict):
                for v in res.values():
                    if isinstance(v, dict) and v.get("href"):
                        print(f"Download: {v['href']}")
                        break
            break
        if s in ("failed", "error"):
            print(f"Error: {r2.json().get('message', '')}")
            break
else:
    print(r.text[:300])

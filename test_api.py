import requests

KEY="32be...BASE = "https://avoin-paikkatieto.maanmittauslaitos.fi/kiinteisto-avoin/simple-features/v3"
BBOX = "384000,6669000,387000,6672000"

r = requests.get(
    f"{BASE}/collections/PalstanSijaintitiedot/items",
    params={"bbox": BBOX, "bbox-crs": "http://www.opengis.net/def/crs/EPSG/0/3067",
            "limit": 3},
    auth=(KEY, ""), timeout=30
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"Features: {len(data.get('features',[]))}")
    if data.get("features"):
        print(f"First props: {data['features'][0]['properties']}")
    links = data.get("links", [])
    next_link = [l for l in links if l.get("rel") == "next"]
    print(f"Next link: {next_link[0] if next_link else 'none'}")
    print(f"Number returned: {data.get('numberReturned')}")
    print(f"Number matched: {data.get('numberMatched')}")
else:
    print(r.text[:500])

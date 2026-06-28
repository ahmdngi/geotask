"""
Interactive city picker.

Starts a local server, opens a Leaflet city picker page.
On save: writes AOI to config, runs all fetch scripts, then shuts down.
"""

import json, os, subprocess, sys, webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
_CONFIG_DIR = _PROJECT_ROOT / "config"
_TEMPLATE_DIR = _PROJECT_ROOT / "templates"
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts" / "fetching"
_PORT = 8765

FETCH_SCRIPTS = [
    "fetch_fingrid.py", "fetch_osm.py", "fetch_urban_centers.py",
    "fetch_natura2000.py", "fetch_flood_zones.py", "fetch_nature_reserves.py",
    "fetch_land_parcels.py", "fetch_dem.py",
]


class PickerHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/city_picker.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write((_TEMPLATE_DIR / "city_picker.html").read_bytes())
        else:
            super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/save":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length))
        city = data.get("city", "Unknown")
        center = data.get("center_wgs84", data.get("bbox_wgs84", []))
        buffer_km = data.get("buffer_km", 100)

        if len(center) == 4:  # legacy bbox
            center = [(center[0] + center[2]) / 2, (center[1] + center[3]) / 2]

        from config.config import set_aoi
        set_aoi(city, center, buffer_km)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

        print(f"\n{'='*50}")
        print(f"  Fetching data for {city}...")
        print(f"{'='*50}\n")

        for script in FETCH_SCRIPTS:
            sp = _SCRIPTS_DIR / script
            if not sp.exists():
                print(f"  SKIP: {script} not found")
                continue
            print(f"── {script} ──", flush=True)
            try:
                r = subprocess.run([sys.executable, str(sp)], timeout=1800,
                                   env={**os.environ, "PYTHONUNBUFFERED": "1"})
                if r.returncode != 0:
                    print(f"  ❌ FAILED (exit {r.returncode})")
            except subprocess.TimeoutExpired:
                print(f"  ⌛ TIMEOUT (1800s)")
            print()

        print(f"{'='*50}")
        print(f"  Done — all scripts finished")
        print(f"{'='*50}")
        self.server.shutdown()

    def log_message(self, fmt, *args):
        if "POST" in str(args) or "GET /city_picker" in str(args):
            print(f"  [{self.address_string()}] {' '.join(str(a) for a in args)}")


def main():
    server = HTTPServer(("127.0.0.1", _PORT), PickerHandler)
    url = f"http://127.0.0.1:{_PORT}/"
    print("-" * 50)
    print("  City Picker")
    print("-" * 50)
    print(f"\n  Open: {url}")
    print(f"\n  Click a city → Save & Close")
    print(f"  → 8 fetch scripts run, then server exits.\n")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()

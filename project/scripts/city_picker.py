"""
Interactive Leaflet city picker for KRIOS GIS.

Starts a local HTTP server, opens the Leaflet city picker page,
saves the selected city + bbox to config/aoi.json,
then automatically runs all data-fetching scripts.
"""

import json
import os
import subprocess
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
_CONFIG_DIR = _PROJECT_ROOT / "config"
_TEMPLATE_DIR = _PROJECT_ROOT / "templates"
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_PORT = 8765

ALL_FETCH_SCRIPTS = [
    "fetching/fetch_fingrid.py",
    "fetching/fetch_osm.py",
    "fetching/fetch_urban_centers.py",
    "fetching/fetch_natura2000.py",
    "fetching/fetch_flood_zones.py",
    "fetching/fetch_nature_reserves.py",
    "fetching/fetch_land_parcels.py",
    "fetching/fetch_dem.py",
]


class PickerHandler(SimpleHTTPRequestHandler):
    """Serve city_picker.html from templates/, handle /save POST."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/city_picker.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = (_TEMPLATE_DIR / "city_picker.html").read_bytes()
            self.wfile.write(html)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/save":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)

            city = data.get("city", "Unknown")
            center = data.get("center_wgs84", data.get("bbox_wgs84", []))
            buffer_km = data.get("buffer_km", 100)

            if len(center) == 4:  # legacy bbox format — estimate center
                lat_center = (center[0] + center[2]) / 2
                lon_center = (center[1] + center[3]) / 2
                center = [lat_center, lon_center]

            from config.config import set_aoi
            set_aoi(city, center, buffer_km)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

            # Auto-run fetching after saving
            print(f"\n{'═' * 50}")
            print(f"  Starting data fetch for {city}...")
            print(f"{'═' * 50}\n")

            for script in ALL_FETCH_SCRIPTS:
                script_path = _SCRIPTS_DIR / script
                if not script_path.exists():
                    print(f"  SKIP: {script} not found")
                    continue

                print(f"── {script} ──", flush=True)
                env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                result = subprocess.run(
                    [sys.executable, str(script_path)],
                    cwd=_PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=env,
                    timeout=600,
                )

                if result.returncode == 0:
                    lines = [l for l in result.stdout.split("\n") if l.strip()]
                    for line in lines[-3:]:
                        print(f"  {line}")
                else:
                    print(f"  ❌ Script failed (exit code {result.returncode})")
                    stderr = result.stderr.strip()
                    stdout = result.stdout.strip()
                    if stderr:
                        print(f"  Stderr: {stderr[:500]}")
                    if stdout:
                        last = [l for l in stdout.split("\n") if l.strip()][-3:]
                        for line in last:
                            print(f"  {line}")
                print()

            print(f"{'═' * 50}")
            print(f"  ✅ All fetching complete for {city}")
            print(f"  📁 Output: {_PROJECT_ROOT / 'data' / 'raw'}/")
            print(f"{'═' * 50}")

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        # Quieter logs
        if "POST" in str(args) or "GET /city_picker" in str(args):
            print(f"  [{self.address_string()}] {' '.join(str(a) for a in args)}")


def main():
    server = HTTPServer(("127.0.0.1", _PORT), PickerHandler)
    url = f"http://127.0.0.1:{_PORT}/city_picker.html"

    print("─" * 50)
    print("  KRIOS GIS — City Picker")
    print("─" * 50)
    print(f"\n  Open in your browser:")
    print(f"  └─ {url}")
    print(f"\n  Click a city marker → 'Save & Close'")
    print(f"  → all 8 fetch scripts run automatically\n")
    print("  Press Ctrl+C to stop.\n")

    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()

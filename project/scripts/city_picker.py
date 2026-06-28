"""
Interactive Leaflet city picker for KRIOS GIS.

Starts a local HTTP server, opens the Leaflet city picker page,
and saves the selected city + bbox to config/aoi.json.
"""

import json
import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_PORT = 8765


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
            bbox = data.get("bbox_wgs84", [])

            aoi = {"city": city, "bbox_wgs84": bbox}
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(_CONFIG_DIR / "aoi.json", "w") as f:
                json.dump(aoi, f, indent=2)

            print(f"\n✅ AOI saved: {city} — bbox {bbox}")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
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
    print(f"\n  Click a city marker → confirm with 'Save & Close'")
    print(f"  Then run: python scripts/run_all.py\n")
    print("  Press Ctrl+C to stop.\n")

    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()

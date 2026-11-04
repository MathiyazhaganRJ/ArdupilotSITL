import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import time
import os
import sys
import threading
import webbrowser

PORT = 8088
VISUALIZER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'visualizer'))

# OpenSky In-Memory Cache (10-second TTL to adhere to OpenSky rate limits)
opensky_cache = {
    'timestamp': 0,
    'last_lat': None,
    'last_lon': None,
    'data': []
}

class HudServerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=VISUALIZER_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        # Direct root and default index requests to the primary Sharkee HUD visualizer
        if parsed.path in ('/', '/index.html'):
            self.send_response(302)
            self.send_header('Location', '/sharkee_hud.html')
            self.end_headers()
            return
        elif parsed.path == '/api/opensky':
            self.handle_opensky(parsed.query)
        else:
            super().do_GET()

    def handle_opensky(self, query_string):
        params = urllib.parse.parse_qs(query_string)
        try:
            lat = float(params.get('lat', [8.3113])[0])
            lon = float(params.get('lon', [77.3077])[0])
        except (ValueError, TypeError):
            lat, lon = 8.3113, 77.3077

        now = time.time()
        # Use cache if within 10 seconds and coordinates are within 0.1 degree
        cache_valid = (
            (now - opensky_cache['timestamp'] < 10.0) and
            opensky_cache['last_lat'] is not None and
            abs(opensky_cache['last_lat'] - lat) < 0.1 and
            abs(opensky_cache['last_lon'] - lon) < 0.1
        )

        if cache_valid:
            payload = {'status': 'ok', 'source': 'cache', 'states': opensky_cache['data']}
        else:
            # Query OpenSky with +/- 0.5 deg (~55km radius) bounding box
            lamin = lat - 0.45
            lamax = lat + 0.45
            lomin = lon - 0.45
            lomax = lon + 0.45
            url = f"https://opensky-network.org/api/states/all?lamin={lamin:.4f}&lomin={lomin:.4f}&lamax={lamax:.4f}&lomax={lomax:.4f}"
            req = urllib.request.Request(url, headers={'User-Agent': 'KarshakAvionics-HUD/1.0'})
            try:
                with urllib.request.urlopen(req, timeout=4.5) as resp:
                    raw = json.loads(resp.read().decode('utf-8'))
                    states = raw.get('states') or []
                    opensky_cache['timestamp'] = now
                    opensky_cache['last_lat'] = lat
                    opensky_cache['last_lon'] = lon
                    opensky_cache['data'] = states
                    payload = {'status': 'ok', 'source': 'live', 'states': states}
            except Exception as e:
                # Fallback to cached data or empty on network timeout/rate-limit
                payload = {'status': 'error', 'message': str(e), 'states': opensky_cache['data']}

        body = json.dumps(payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress routine 200 GET logs to keep terminal quiet
        if len(args) > 1 and args[1] == '200':
            return
        super().log_message(format, *args)

def open_browser(url):
    import platform
    import subprocess
    import shutil
    time.sleep(0.6)
    is_wsl = 'microsoft' in platform.uname().release.lower() or os.path.exists('/proc/sys/fs/binfmt_misc/WSLInterop')
    if is_wsl:
        if shutil.which("cmd.exe"):
            try:
                subprocess.Popen(["cmd.exe", "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
        if shutil.which("powershell.exe"):
            try:
                subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{url}'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
    try:
        webbrowser.open(url)
    except Exception:
        pass

def run():
    target_url = f"http://localhost:{PORT}/sharkee_hud.html"
    print("\n" + "=" * 65)
    print(f"[HUD Server] Serving visualizer on: {target_url}")
    print(f"[HUD Server] OpenSky ADS-B proxy endpoint active at /api/opensky")
    print(f"[HUD Server] Launching browser automatically...")
    print(f"[Notice] For full live ArduPilot MAVLink SITL telemetry, run:")
    print(f"         python server.py")
    print("=" * 65 + "\n")

    threading.Thread(target=open_browser, args=(target_url,), daemon=True).start()

    try:
        with http.server.ThreadingHTTPServer(("", PORT), HudServerHandler) as httpd:
            httpd.serve_forever()
    except OSError as e:
        if getattr(e, 'errno', None) in (10048, 98):
            print(f"\n[!] ERROR: Port {PORT} is already in use by another process.")
            print(f"    To free port {PORT}, run in PowerShell:")
            print(f"    Get-Process python | Stop-Process -Force\n")
        else:
            raise

if __name__ == '__main__':
    run()

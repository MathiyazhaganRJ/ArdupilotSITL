import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import time
import os
import sys

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
        if parsed.path == '/api/opensky':
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

def run():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), HudServerHandler) as httpd:
        print(f"[HUD Server] Serving visualizer on http://localhost:{PORT}")
        print(f"[HUD Server] OpenSky ADS-B proxy endpoint active at /api/opensky")
        httpd.serve_forever()

if __name__ == '__main__':
    run()

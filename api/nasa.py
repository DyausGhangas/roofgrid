from http.server import BaseHTTPRequestHandler
import json
import urllib.error
import urllib.parse
import urllib.request


class handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, max-age=86400')
        self.end_headers()
        if isinstance(payload, bytes):
            self.wfile.write(payload)
        else:
            self.wfile.write(json.dumps(payload).encode())

    def do_GET(self):
        try:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            lat = float(params.get('lat', [''])[0])
            lon = float(params.get('lon', [''])[0])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError('coordinates out of range')
            query = urllib.parse.urlencode({
                'parameters': 'ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,T2M',
                'community': 'RE',
                'longitude': lon,
                'latitude': lat,
                'format': 'JSON'
            })
            request = urllib.request.Request(
                f'https://power.larc.nasa.gov/api/temporal/climatology/point?{query}',
                headers={'User-Agent': 'RoofGrid-Global/1.0'}
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                self._json(200, response.read())
        except (ValueError, TypeError):
            self._json(400, {'error': 'Valid latitude and longitude are required'})
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            self._json(502, {'error': 'Global solar climate data is temporarily unavailable'})

    def do_OPTIONS(self):
        self._json(200, {})

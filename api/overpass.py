from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error
import urllib.parse
import json
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("roofgrid.overpass")

REQUEST_TIMEOUT = 8
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
)

# Regex to validate bbox format: "lat,lon,lat,lon" (four comma-separated numbers)
BBOX_PATTERN = re.compile(
    r'^-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*$'
)


def fetch_overpass_data(overpass_query):
    """Return valid Overpass JSON, trying a second public instance if needed."""
    request_data = urllib.parse.urlencode({'data': overpass_query}).encode()

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=request_data, method='POST')
            req.add_header('User-Agent', 'RoofGrid/1.0 (rooftop planning tool)')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            req.add_header('Accept', 'application/json')

            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                result = response.read()

            payload = json.loads(result.decode('utf-8'))
            if not isinstance(payload, dict) or not isinstance(payload.get('elements'), list):
                raise ValueError('Response did not contain an elements list')

            logger.info("Overpass response from %s: %d bytes", endpoint, len(result))
            return result
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            logger.warning("Overpass endpoint %s failed: %s", endpoint, error)

    raise RuntimeError('All configured Overpass endpoints failed')


class handler(BaseHTTPRequestHandler):
    def _send_json_response(self, status_code, data):
        """Helper to send a JSON response with CORS headers."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_GET(self):
        try:
            # Parse query parameters
            parsed_path = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_path.query)

            bbox = query_params.get('bbox', [''])[0]

            if not bbox:
                self._send_json_response(400, {'error': 'Missing bbox parameter'})
                return

            # Validate bbox format to prevent injection
            if not BBOX_PATTERN.match(bbox):
                self._send_json_response(400, {
                    'error': 'Invalid bbox format. Expected: south_lat,west_lon,north_lat,east_lon'
                })
                return

            south, west, north, east = map(float, bbox.split(','))
            if south >= north or west >= east or north - south > 0.05 or east - west > 0.05:
                self._send_json_response(400, {
                    'error': 'Invalid or oversized viewport. Zoom in closer and try again.'
                })
                return

            logger.info("Overpass request: bbox=%s", bbox)

            # Build Overpass query
            overpass_query = f"""
            [out:json][timeout:12];
            (
                way["building"]({bbox});
                relation["building"]({bbox});
            );
            out geom;
            """

            result = fetch_overpass_data(overpass_query)

            # Send success response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=600')
            self.end_headers()
            self.wfile.write(result)

        except RuntimeError as error:
            logger.error("Overpass providers unavailable: %s", error)
            self._send_json_response(502, {
                'error': 'Building outline service is temporarily unavailable. Please try again in a moment.'
            })

        except Exception as e:
            logger.exception("Unexpected error in Overpass handler")
            self._send_json_response(500, {
                'error': 'Internal server error. Please try again later.'
            })

from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error
import urllib.parse
import json
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("roofgrid.overpass")

REQUEST_TIMEOUT = 15  # seconds (safe margin for Vercel's 30s limit)

# Regex to validate bbox format: "lat,lon,lat,lon" (four comma-separated numbers)
BBOX_PATTERN = re.compile(
    r'^-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*$'
)


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
            [out:json][timeout:25];
            (
                way["building"]({bbox});
                relation["building"]({bbox});
            );
            out geom;
            """

            # Query Overpass API
            overpass_url = "https://overpass-api.de/api/interpreter"
            data = urllib.parse.urlencode({'data': overpass_query}).encode()

            req = urllib.request.Request(overpass_url, data=data, method='POST')
            req.add_header('User-Agent', 'Mozilla/5.0 (compatible; RoofGrid/1.0)')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                result = response.read()

            logger.info("Overpass response: %d bytes", len(result))

            # Send success response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(result)

        except urllib.error.HTTPError as e:
            logger.error("Overpass API HTTP %d", e.code)
            self._send_json_response(502, {
                'error': 'Building data service temporarily unavailable. Please try again.'
            })

        except urllib.error.URLError as e:
            logger.error("Overpass network error: %s", e.reason)
            self._send_json_response(502, {
                'error': 'Network error when fetching building data. Please try again.'
            })

        except Exception as e:
            logger.exception("Unexpected error in Overpass handler")
            self._send_json_response(500, {
                'error': 'Internal server error. Please try again later.'
            })

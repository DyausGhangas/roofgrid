#!/usr/bin/env python3
"""
Enhanced Local HTTP Server for RoofGrid
Includes proxies for Overpass API and OpenAI-compatible AI providers
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import urllib.error
import json
import os
import logging
import re
from email.utils import parseaddr
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("roofgrid")

PORT = 8000
REQUEST_TIMEOUT = 15  # seconds
MAX_CONTACT_REQUEST_SIZE = 16 * 1024
NASA_CACHE = {}

# Regex to validate bbox format
BBOX_PATTERN = re.compile(
    r'^-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*$'
)

def load_local_environment():
    """Load project environment files without overriding shell variables.

    `.env.local` is loaded after `.env`, so developers can keep private local
    overrides in the same file name used by common deployment workflows.
    """
    project_root = Path(__file__).parent
    shell_keys = set(os.environ)
    loaded_files = []

    for filename in (".env", ".env.local"):
        env_path = project_root / filename
        if not env_path.is_file():
            continue

        with env_path.open(encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                if key and key not in shell_keys:
                    os.environ[key] = value

        loaded_files.append(filename)

    if loaded_files:
        logger.info("Loaded local environment settings from %s", ", ".join(loaded_files))
    else:
        logger.warning("No .env or .env.local file found — using shell environment variables")


load_local_environment()

AI_PROVIDER_DEFAULTS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4.1-mini"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4.1-mini"),
}
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").strip().lower()
default_endpoint, default_model = AI_PROVIDER_DEFAULTS.get(AI_PROVIDER, ("", ""))
configured_ai_key = os.getenv("AI_API_KEY", "").strip()
legacy_groq_key = os.getenv("GROQ_API_KEY", "").strip()
if "your_" in configured_ai_key.lower():
    configured_ai_key = ""
if "your_" in legacy_groq_key.lower():
    legacy_groq_key = ""
AI_API_KEY = configured_ai_key or legacy_groq_key
AI_ENDPOINT = os.getenv("AI_BASE_URL", "").strip() or default_endpoint
AI_MODEL = os.getenv("AI_MODEL", "").strip() or default_model
AI_AUTH_HEADER = os.getenv("AI_AUTH_HEADER", "Authorization").strip()
AI_AUTH_SCHEME = os.getenv("AI_AUTH_SCHEME", "Bearer").strip()
AI_ALLOW_NO_AUTH = os.getenv("AI_ALLOW_NO_AUTH", "false").strip().lower() in ("1", "true", "yes")
AI_CONFIGURED = bool(
    AI_ENDPOINT
    and AI_MODEL
    and (AI_API_KEY or AI_ALLOW_NO_AUTH)
)
if not AI_CONFIGURED:
    logger.warning("AI API is not configured — add GROQ_API_KEY to .env.local or the shell environment")
else:
    logger.info("AI provider configured: %s (%s)", AI_PROVIDER, AI_MODEL)


def prepare_ai_payload(request_data):
    """Apply the server-selected model and provider-specific compatibility fields."""
    request_data["model"] = AI_MODEL
    if AI_PROVIDER == "groq" and AI_MODEL.startswith("openai/gpt-oss"):
        token_limit = request_data.pop("max_tokens", None)
        if token_limit is not None:
            request_data["max_completion_tokens"] = token_limit
        request_data.setdefault("reasoning_effort", "low")
        request_data.setdefault("include_reasoning", False)
    return json.dumps(request_data).encode("utf-8")

class ProxyRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def do_GET(self):
        if self.path.startswith('/api/nasa'):
            try:
                params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                lat = float(params.get('lat', [''])[0])
                lon = float(params.get('lon', [''])[0])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError('coordinates out of range')
                cache_key = f'{lat:.2f},{lon:.2f}'
                if cache_key in NASA_CACHE:
                    result = NASA_CACHE[cache_key]
                else:
                    nasa_params = urllib.parse.urlencode({
                        'parameters': 'ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,T2M',
                        'community': 'RE',
                        'longitude': lon,
                        'latitude': lat,
                        'format': 'JSON'
                    })
                    url = f'https://power.larc.nasa.gov/api/temporal/climatology/point?{nasa_params}'
                    req = urllib.request.Request(url, headers={'User-Agent': 'RoofGrid-Global/1.0'})
                    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                        result = response.read()
                    NASA_CACHE[cache_key] = result
                    if len(NASA_CACHE) > 100:
                        NASA_CACHE.pop(next(iter(NASA_CACHE)))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                self.wfile.write(result)
            except (ValueError, TypeError):
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Valid latitude and longitude are required'}).encode())
            except Exception as e:
                logger.error('NASA POWER request failed: %s', e)
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Global solar climate data is temporarily unavailable'}).encode())
            return

        # Proxy endpoint for Overpass API
        if self.path.startswith('/api/overpass'):
            try:
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                
                bbox = params.get('bbox', [''])[0]
                
                if not bbox:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    error_data = json.dumps({'error': 'Missing bbox parameter'})
                    self.wfile.write(error_data.encode())
                    return

                # Validate bbox format
                if not BBOX_PATTERN.match(bbox):
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Invalid bbox format. Expected: south_lat,west_lon,north_lat,east_lon'
                    }).encode())
                    return

                south, west, north, east = map(float, bbox.split(','))
                if south >= north or west >= east or north - south > 0.05 or east - west > 0.05:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Invalid or oversized viewport. Zoom in closer and try again.'
                    }).encode())
                    return
                
                overpass_query = f"""
                [out:json][timeout:25];
                (
                    way["building"]({bbox});
                    relation["building"]({bbox});
                );
                out geom;
                """
                
                logger.info("Overpass request: bbox=%s", bbox)
                
                overpass_url = "https://overpass-api.de/api/interpreter"
                data = urllib.parse.urlencode({'data': overpass_query}).encode()
                
                req = urllib.request.Request(overpass_url, data=data, method='POST')
                req.add_header('User-Agent', 'RoofGrid-Global/1.0')
                req.add_header('Content-Type', 'application/x-www-form-urlencoded')
                
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                    result = response.read()
                
                logger.info("Overpass response: %d bytes", len(result))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(result)
                
            except urllib.error.HTTPError as e:
                logger.error("Overpass API HTTP %d", e.code)
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': 'Building data service unavailable. Please try again.'
                }).encode())
            except urllib.error.URLError as e:
                logger.error("Overpass network error: %s", e.reason)
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': 'Network error. Please try again.'
                }).encode())
            except Exception as e:
                logger.exception("Overpass proxy error")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': 'Internal server error'
                }).encode())
        
        else:
            # Serve static files normally
            super().do_GET()
    
    def do_POST(self):
        if self.path.startswith('/api/contact'):
            self.handle_contact_request()
            return

        # Provider-agnostic proxy for OpenAI-compatible chat-completions APIs.
        if self.path.startswith('/api/ai') or self.path.startswith('/api/groq'):
            if not AI_CONFIGURED:
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': {
                        'message': 'AI assistant is not configured. Add GROQ_API_KEY to .env.local, or configure another OpenAI-compatible provider.',
                        'type': 'configuration_error'
                    }
                }).encode())
                return
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                
                logger.info("AI request body: %d bytes", content_length)
                
                # Parse the request to validate
                try:
                    request_data = json.loads(body.decode('utf-8'))
                    body = prepare_ai_payload(request_data)
                    logger.info("AI request: provider=%s model=%s", AI_PROVIDER, AI_MODEL)
                except Exception as parse_err:
                    logger.warning("Could not parse request: %s", parse_err)
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': {'message': 'Invalid JSON request body'}}).encode())
                    return
                
                # Create request with proper headers to avoid Cloudflare blocking
                req = urllib.request.Request(AI_ENDPOINT, data=body, method='POST')
                req.add_header('Content-Type', 'application/json')
                if AI_API_KEY:
                    auth_value = f'{AI_AUTH_SCHEME} {AI_API_KEY}'.strip()
                    req.add_header(AI_AUTH_HEADER, auth_value)
                req.add_header('User-Agent', 'RoofGrid/1.0')
                req.add_header('Accept', 'application/json')
                
                try:
                    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                        result = response.read()
                        status = response.getcode()
                    
                    logger.info("AI response: provider=%s status=%d", AI_PROVIDER, status)
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(result)
                    
                except urllib.error.HTTPError as http_err:
                    error_body = http_err.read().decode('utf-8') if http_err.fp else str(http_err)
                    logger.error("AI provider HTTP %d: %s", http_err.code, error_body[:200])
                    
                    # Return error to frontend
                    self.send_response(http_err.code)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    
                    upstream_message = error_body
                    try:
                        upstream_error = json.loads(error_body)
                        if isinstance(upstream_error, dict):
                            error_value = upstream_error.get("error", upstream_error)
                            if isinstance(error_value, dict):
                                upstream_message = error_value.get("message", error_body)
                            elif isinstance(error_value, str):
                                upstream_message = error_value
                    except (json.JSONDecodeError, TypeError):
                        pass

                    error_response = {
                        "error": {
                            "message": upstream_message,
                            "type": "api_error",
                            "code": http_err.code
                        }
                    }
                    self.wfile.write(json.dumps(error_response).encode())
                
            except Exception as e:
                logger.exception("AI proxy error")
                
                # Return error response
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                error_response = {
                    "error": {
                        "message": str(e),
                        "type": "server_error"
                    }
                }
                self.wfile.write(json.dumps(error_response).encode())
        else:
            self.send_response(405)
            self.end_headers()

    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def handle_contact_request(self):
        recipient = os.getenv('CONTACT_EMAIL', '').strip()
        if not recipient or recipient.lower() == 'you@example.com':
            self.send_json(503, {'error': 'Contact delivery is not configured.'})
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0 or content_length > MAX_CONTACT_REQUEST_SIZE:
                self.send_json(413 if content_length > MAX_CONTACT_REQUEST_SIZE else 400, {
                    'error': 'Invalid contact request size.'
                })
                return

            payload = json.loads(self.rfile.read(content_length).decode('utf-8'))
            sender = str(payload.get('email', '')).strip()
            subject = str(payload.get('_subject', payload.get('subject', ''))).strip()
            message = str(payload.get('message', '')).strip()
            honey = str(payload.get('_honey', payload.get('website', ''))).strip()

            parsed_email = parseaddr(sender)[1]
            valid_email = parsed_email == sender and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', sender)
            if honey:
                self.send_json(200, {'success': True})
                return
            if not valid_email or not 2 <= len(subject) <= 120 or not 10 <= len(message) <= 4000:
                self.send_json(400, {'error': 'Enter a valid email, subject, and message.'})
                return

            form_data = json.dumps({
                'email': sender,
                '_replyto': sender,
                '_subject': subject,
                'message': message,
                '_template': 'table',
                '_captcha': 'false',
            }).encode('utf-8')
            endpoint = f"https://formsubmit.co/ajax/{urllib.parse.quote(recipient, safe='@')}"
            request = urllib.request.Request(endpoint, data=form_data, method='POST')
            request.add_header('Content-Type', 'application/json')
            request.add_header('Accept', 'application/json')
            request.add_header('User-Agent', 'RoofGrid/1.0')
            origin = self.headers.get('Origin', '')
            referer = self.headers.get('Referer', '')
            if origin.startswith(('https://', 'http://')):
                request.add_header('Origin', origin)
            if referer.startswith(('https://', 'http://')):
                request.add_header('Referer', referer)

            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                response_body = response.read()
                status = response.getcode()

            try:
                provider_result = json.loads(response_body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                provider_result = {}

            provider_success = provider_result.get('success', True)
            if provider_success in (False, 'false', 0, '0'):
                message = provider_result.get('message', 'Contact service could not deliver the message.')
                self.send_json(502, {'success': False, 'error': message})
            elif 200 <= status < 300:
                self.send_json(200, {
                    'success': True,
                    'message': provider_result.get('message', 'Message accepted for delivery.'),
                })
            else:
                self.send_json(502, {'error': 'Contact service rejected the message.'})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {'error': 'Invalid contact request.'})
        except urllib.error.HTTPError as error:
            logger.error('Contact service HTTP %d', error.code)
            self.send_json(502, {'error': 'Contact service could not deliver the message.'})
        except urllib.error.URLError as error:
            logger.error('Contact service network error: %s', error.reason)
            self.send_json(502, {'error': 'Contact service is unavailable.'})
        except Exception:
            logger.exception('Contact proxy error')
            self.send_json(500, {'error': 'The message could not be sent.'})

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    Handler = ProxyRequestHandler
    
    # Change to the project directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    with ReusableTCPServer(("", PORT), Handler) as httpd:
        logger.info("=" * 55)
        logger.info("RoofGrid Local Server Running!")
        logger.info("=" * 55)
        logger.info("Main App:      http://localhost:%d/solar_advanced.html", PORT)
        logger.info("Landing Page:  http://localhost:%d/index.html", PORT)
        logger.info("Overpass Proxy: http://localhost:%d/api/overpass", PORT)
        logger.info("AI Proxy:       http://localhost:%d/api/ai", PORT)
        logger.info("=" * 55)
        logger.info("Press Ctrl+C to stop the server")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("RoofGrid local server stopped")

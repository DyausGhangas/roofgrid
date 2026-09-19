"""AWS Lambda entry point for RoofGrid's server-side routes."""

import base64
from email.utils import parseaddr
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request


logger = logging.getLogger("roofgrid.aws")
logger.setLevel(logging.INFO)

AI_PROVIDER_DEFAULTS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4.1-mini"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4.1-mini"),
}
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
)
BBOX_PATTERN = re.compile(r"^-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*$")
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_runtime_config_cache = None


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": os.getenv("ALLOWED_ORIGIN", "*"),
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }


def _response(status_code, payload, extra_headers=None):
    headers = _cors_headers()
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(payload, separators=(",", ":")),
        "isBase64Encoded": False,
    }


def _event_body(event, maximum_size):
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")
    if not isinstance(raw_body, str) or not raw_body:
        raise ValueError("Empty request body")
    if len(raw_body.encode("utf-8")) > maximum_size:
        raise OverflowError("Request body too large")
    return json.loads(raw_body)


def _runtime_config():
    """Load private configuration once per warm Lambda environment."""
    global _runtime_config_cache
    if _runtime_config_cache is not None:
        return _runtime_config_cache

    config = {
        key: os.getenv(key, "").strip()
        for key in (
            "GROQ_API_KEY",
            "CONTACT_EMAIL",
            "AI_API_KEY",
            "AI_BASE_URL",
            "AI_AUTH_HEADER",
            "AI_AUTH_SCHEME",
            "AI_ALLOW_NO_AUTH",
        )
    }
    secret_arn = os.getenv("ROOFGRID_SECRET_ARN", "").strip()
    if secret_arn:
        try:
            import boto3

            secret = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
            secret_text = secret.get("SecretString", "")
            if not secret_text and secret.get("SecretBinary"):
                secret_text = base64.b64decode(secret["SecretBinary"]).decode("utf-8")
            secret_values = json.loads(secret_text)
            if not isinstance(secret_values, dict):
                raise ValueError("RoofGrid secret must contain a JSON object")
            for key, value in secret_values.items():
                if key in config and value is not None:
                    config[key] = str(value).strip()
        except Exception:
            logger.exception("Unable to load RoofGrid configuration from Secrets Manager")

    _runtime_config_cache = config
    return config


def _request_headers(event):
    return {str(key).lower(): str(value) for key, value in (event.get("headers") or {}).items()}


def _query_parameters(event):
    return event.get("queryStringParameters") or {}


def _handle_ai(event):
    config = _runtime_config()
    provider = os.getenv("AI_PROVIDER", "groq").strip().lower()
    default_endpoint, default_model = AI_PROVIDER_DEFAULTS.get(provider, ("", ""))
    configured_key = config.get("AI_API_KEY", "")
    groq_key = config.get("GROQ_API_KEY", "")
    if "your_" in configured_key.lower():
        configured_key = ""
    if "replace_with" in groq_key.lower() or "your_" in groq_key.lower():
        groq_key = ""

    api_key = configured_key or groq_key
    endpoint = config.get("AI_BASE_URL", "") or default_endpoint
    model = os.getenv("AI_MODEL", "").strip() or default_model
    allow_no_auth = config.get("AI_ALLOW_NO_AUTH", "").lower() in ("1", "true", "yes")
    if not endpoint or not model or (not api_key and not allow_no_auth):
        return _response(503, {"error": "AI is not configured on this deployment."})

    try:
        payload = _event_body(event, 64 * 1024)
    except OverflowError as error:
        return _response(413, {"error": str(error)})
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return _response(400, {"error": "Invalid AI request."})

    if not isinstance(payload, dict):
        return _response(400, {"error": "Invalid AI request."})
    payload["model"] = model
    if provider == "groq" and model.startswith("openai/gpt-oss"):
        token_limit = payload.pop("max_tokens", None)
        if token_limit is not None:
            payload["max_completion_tokens"] = token_limit
        payload.setdefault("reasoning_effort", "low")
        payload.setdefault("include_reasoning", False)

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "RoofGrid/1.0"},
    )
    if api_key:
        auth_header = config.get("AI_AUTH_HEADER", "") or "Authorization"
        auth_scheme = config.get("AI_AUTH_SCHEME", "") or "Bearer"
        request.add_header(auth_header, f"{auth_scheme} {api_key}".strip())

    try:
        with urllib.request.urlopen(request, timeout=15) as upstream:
            result = json.loads(upstream.read().decode("utf-8"))
            return _response(upstream.getcode(), result)
    except urllib.error.HTTPError as error:
        try:
            upstream_body = json.loads(error.read().decode("utf-8"))
            value = upstream_body.get("error", upstream_body)
            message = value.get("message") if isinstance(value, dict) else str(value)
        except Exception:
            message = "The AI provider rejected the request."
        logger.warning("AI provider returned HTTP %s", error.code)
        return _response(error.code, {"error": message, "status": error.code})
    except (urllib.error.URLError, TimeoutError):
        logger.exception("AI provider is unavailable")
        return _response(502, {"error": "The AI service is temporarily unavailable."})
    except Exception:
        logger.exception("Unexpected AI proxy error")
        return _response(500, {"error": "The AI request could not be completed."})


def _handle_contact(event):
    recipient = _runtime_config().get("CONTACT_EMAIL", "")
    if not recipient or recipient.lower() == "you@example.com":
        return _response(503, {"error": "Contact delivery is not configured."})

    try:
        payload = _event_body(event, 16 * 1024)
    except OverflowError:
        return _response(413, {"error": "Contact request is too large."})
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return _response(400, {"error": "Invalid contact request."})

    sender = str(payload.get("email", "")).strip()
    subject = str(payload.get("_subject", payload.get("subject", ""))).strip()
    message = str(payload.get("message", "")).strip()
    honey = str(payload.get("_honey", payload.get("website", ""))).strip()
    if honey:
        return _response(200, {"success": True})
    parsed_email = parseaddr(sender)[1]
    valid_email = parsed_email == sender and EMAIL_PATTERN.fullmatch(sender)
    if not valid_email or not 2 <= len(subject) <= 120 or not 10 <= len(message) <= 4000:
        return _response(400, {"error": "Enter a valid email, subject, and message."})

    form_data = json.dumps({
        "email": sender,
        "_replyto": sender,
        "_subject": subject,
        "message": message,
        "_template": "table",
        "_captcha": "false",
    }).encode("utf-8")
    endpoint = f"https://formsubmit.co/ajax/{urllib.parse.quote(recipient, safe='@')}"
    request = urllib.request.Request(endpoint, data=form_data, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "RoofGrid/1.0")
    request_headers = _request_headers(event)
    for header in ("origin", "referer"):
        value = request_headers.get(header, "")
        if value.startswith(("https://", "http://")):
            request.add_header(header.title(), value)

    try:
        with urllib.request.urlopen(request, timeout=15) as upstream:
            result = json.loads(upstream.read().decode("utf-8"))
            provider_success = result.get("success", True)
            if provider_success in (False, "false", 0, "0"):
                return _response(502, {
                    "success": False,
                    "error": result.get("message", "Contact service could not deliver the message."),
                })
            return _response(200, {
                "success": True,
                "message": result.get("message", "Message accepted for delivery."),
            })
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        logger.exception("Contact delivery service is unavailable")
        return _response(502, {"error": "Contact service could not deliver the message."})
    except Exception:
        logger.exception("Unexpected contact proxy error")
        return _response(500, {"error": "The message could not be sent."})


def _handle_nasa(event):
    params = _query_parameters(event)
    try:
        latitude = float(params.get("lat", ""))
        longitude = float(params.get("lon", ""))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("coordinates out of range")
    except (ValueError, TypeError):
        return _response(400, {"error": "Valid latitude and longitude are required"})

    query = urllib.parse.urlencode({
        "parameters": "ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,T2M",
        "community": "RE",
        "longitude": longitude,
        "latitude": latitude,
        "format": "JSON",
    })
    request = urllib.request.Request(
        f"https://power.larc.nasa.gov/api/temporal/climatology/point?{query}",
        headers={"User-Agent": "RoofGrid-Global/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as upstream:
            result = json.loads(upstream.read().decode("utf-8"))
        return _response(200, result, {"Cache-Control": "public, max-age=86400"})
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        logger.exception("NASA POWER API is unavailable")
        return _response(502, {"error": "Global solar climate data is temporarily unavailable"})


def _handle_overpass(event):
    bbox = str(_query_parameters(event).get("bbox", ""))
    if not bbox:
        return _response(400, {"error": "Missing bbox parameter"})
    if not BBOX_PATTERN.fullmatch(bbox):
        return _response(400, {
            "error": "Invalid bbox format. Expected: south_lat,west_lon,north_lat,east_lon"
        })

    south, west, north, east = map(float, bbox.split(","))
    if south >= north or west >= east or north - south > 0.05 or east - west > 0.05:
        return _response(400, {"error": "Invalid or oversized viewport. Zoom in closer and try again."})
    overpass_query = f"""
    [out:json][timeout:12];
    (
        way[\"building\"]({bbox});
        relation[\"building\"]({bbox});
    );
    out geom;
    """
    request_data = urllib.parse.urlencode({"data": overpass_query}).encode("utf-8")

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            request = urllib.request.Request(endpoint, data=request_data, method="POST")
            request.add_header("User-Agent", "RoofGrid/1.0 (rooftop planning tool)")
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            request.add_header("Accept", "application/json")
            with urllib.request.urlopen(request, timeout=8) as upstream:
                result = json.loads(upstream.read().decode("utf-8"))
            if not isinstance(result, dict) or not isinstance(result.get("elements"), list):
                raise ValueError("Invalid Overpass response")
            return _response(200, result, {
                "Cache-Control": "public, max-age=300, stale-while-revalidate=600"
            })
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                UnicodeDecodeError, json.JSONDecodeError, ValueError):
            logger.warning("Overpass endpoint failed: %s", endpoint)

    return _response(502, {
        "error": "Building outline service is temporarily unavailable. Please try again in a moment."
    })


def lambda_handler(event, _context):
    request_context = event.get("requestContext") or {}
    http_context = request_context.get("http") or {}
    method = str(http_context.get("method") or event.get("httpMethod") or "GET").upper()
    path = str(event.get("rawPath") or http_context.get("path") or event.get("path") or "/")

    if method == "OPTIONS":
        return _response(204, {})
    if method == "GET" and path == "/api/health":
        return _response(200, {"status": "ok", "service": "roofgrid-api"}, {
            "Cache-Control": "no-store"
        })
    if method == "POST" and path in ("/api/ai", "/api/groq"):
        return _handle_ai(event)
    if method == "POST" and path == "/api/contact":
        return _handle_contact(event)
    if method == "GET" and path == "/api/nasa":
        return _handle_nasa(event)
    if method == "GET" and path == "/api/overpass":
        return _handle_overpass(event)
    return _response(404, {"error": "Route not found"})

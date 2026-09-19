"""AWS Lambda entry point for RoofGrid's server-side routes."""

import base64
from datetime import datetime, timedelta, timezone
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

BEDROCK_MODEL_DEFAULT = "openai.gpt-oss-120b-1:0"
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
        "CONTACT_EMAIL": os.getenv("CONTACT_EMAIL", "").strip(),
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


def _message_text(content):
    """Convert an OpenAI-style message content value to plain text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def _converse_messages(messages):
    """Map OpenAI-style chat messages to the Bedrock Converse structure."""
    system = []
    conversation = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).strip().lower()
        text = _message_text(message.get("content"))
        if not text:
            continue

        if role in ("system", "developer"):
            system.append({"text": text})
        elif role in ("user", "assistant"):
            conversation.append({
                "role": role,
                "content": [{"text": text}],
            })

    return system, conversation


def _openai_response_from_converse(response, model):
    """Return only user-facing text blocks in the shape expected by the frontend."""
    content_blocks = (
        response.get("output", {})
        .get("message", {})
        .get("content", [])
    )
    text_parts = [
        block["text"]
        for block in content_blocks
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    answer = "\n".join(part for part in text_parts if part).strip()
    if not answer:
        raise ValueError("Bedrock returned no user-facing text")

    usage = response.get("usage") or {}
    return {
        "id": response.get("ResponseMetadata", {}).get("RequestId", "bedrock"),
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": answer,
            },
            "finish_reason": response.get("stopReason", "stop"),
        }],
        "usage": {
            "prompt_tokens": usage.get("inputTokens", 0),
            "completion_tokens": usage.get("outputTokens", 0),
            "total_tokens": usage.get("totalTokens", 0),
        },
    }


def _consume_ai_quota():
    """Atomically enforce the deployment-wide daily Bedrock request cap."""
    table_name = os.getenv("AI_USAGE_TABLE", "").strip()
    try:
        daily_limit = int(os.getenv("AI_DAILY_REQUEST_LIMIT", "100"))
    except ValueError:
        daily_limit = 100

    if not table_name or daily_limit <= 0:
        logger.error("AI quota configuration is missing or invalid")
        return None

    now = datetime.now(timezone.utc)
    quota_key = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    expires_at = int((tomorrow + timedelta(days=2)).timestamp())

    try:
        import boto3
        from botocore.exceptions import ClientError

        dynamodb = boto3.client("dynamodb")
        dynamodb.update_item(
            TableName=table_name,
            Key={"quota_key": {"S": quota_key}},
            UpdateExpression=(
                "SET #count = if_not_exists(#count, :zero) + :one, "
                "expires_at = :expires"
            ),
            ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
            ExpressionAttributeNames={"#count": "request_count"},
            ExpressionAttributeValues={
                ":zero": {"N": "0"},
                ":one": {"N": "1"},
                ":limit": {"N": str(daily_limit)},
                ":expires": {"N": str(expires_at)},
            },
        )
        return True
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        logger.exception("Unable to update RoofGrid AI quota")
        return None
    except Exception:
        logger.exception("Unable to update RoofGrid AI quota")
        return None


def _handle_ai(event):
    try:
        payload = _event_body(event, 64 * 1024)
    except OverflowError as error:
        return _response(413, {"error": str(error)})
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return _response(400, {"error": "Invalid AI request."})

    if not isinstance(payload, dict):
        return _response(400, {"error": "Invalid AI request."})

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return _response(400, {"error": "At least one AI message is required."})

    quota_status = _consume_ai_quota()
    if quota_status is False:
        return _response(429, {
            "error": "RoofGrid AI has reached its daily usage limit. Please try again tomorrow."
        })
    if quota_status is None:
        return _response(503, {
            "error": "RoofGrid AI usage protection is temporarily unavailable."
        })

    model = os.getenv("AI_MODEL", "").strip() or BEDROCK_MODEL_DEFAULT
    token_limit = payload.get("max_completion_tokens", payload.get("max_tokens", 700))
    try:
        token_limit = max(1, min(int(token_limit), 4096))
    except (TypeError, ValueError):
        token_limit = 700

    system_messages, conversation = _converse_messages(messages)
    if not conversation:
        return _response(400, {"error": "At least one user or assistant message is required."})

    inference_config = {
        "maxTokens": token_limit,
        "temperature": payload.get("temperature", 0.3),
        "topP": payload.get("top_p", 0.9),
    }
    stop = payload.get("stop")
    if isinstance(stop, str) and stop:
        inference_config["stopSequences"] = [stop]
    elif isinstance(stop, list):
        stop_sequences = [str(value) for value in stop if str(value)]
        if stop_sequences:
            inference_config["stopSequences"] = stop_sequences

    try:
        import boto3

        bedrock = boto3.client("bedrock-runtime")
        converse_request = {
            "modelId": model,
            "messages": conversation,
            "inferenceConfig": inference_config,
            "additionalModelRequestFields": {
                "reasoning_effort": "low",
            },
        }
        if system_messages:
            converse_request["system"] = system_messages

        upstream = bedrock.converse(**converse_request)
        result = _openai_response_from_converse(upstream, model)
        return _response(200, result)
    except Exception as error:
        response = getattr(error, "response", {}) or {}
        error_info = response.get("Error", {}) if isinstance(response, dict) else {}
        code = str(error_info.get("Code", ""))
        logger.exception("Amazon Bedrock invocation failed: %s", code or type(error).__name__)

        if code in ("AccessDeniedException", "UnauthorizedException"):
            return _response(503, {
                "error": "RoofGrid AI does not have permission to use Amazon Bedrock."
            })
        if code in ("ThrottlingException", "ServiceQuotaExceededException"):
            return _response(429, {
                "error": "RoofGrid AI is busy. Please try again shortly."
            })
        if code in ("ValidationException", "ResourceNotFoundException"):
            return _response(502, {
                "error": "RoofGrid AI model configuration is invalid."
            })
        return _response(502, {
            "error": "RoofGrid AI is temporarily unavailable."
        })


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

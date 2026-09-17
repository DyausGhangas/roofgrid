from http.server import BaseHTTPRequestHandler
import os
import json
import urllib.request
import urllib.error
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("roofgrid.ai")

AI_PROVIDER_DEFAULTS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4.1-mini"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4.1-mini"),
}
REQUEST_TIMEOUT = 15  # seconds (safe margin for Vercel's 30s limit)
MAX_REQUEST_SIZE = 64 * 1024  # 64KB max request body


class handler(BaseHTTPRequestHandler):
    def _send_json_response(self, status_code, data):
        """Helper to send a JSON response with CORS headers."""
        self.send_response(status_code)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_POST(self):
        provider = os.getenv("AI_PROVIDER", "groq").strip().lower()
        default_endpoint, default_model = AI_PROVIDER_DEFAULTS.get(provider, ("", ""))
        configured_ai_key = os.getenv("AI_API_KEY", "").strip()
        legacy_groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if "your_" in configured_ai_key.lower():
            configured_ai_key = ""
        if "your_" in legacy_groq_key.lower():
            legacy_groq_key = ""
        api_key = configured_ai_key or legacy_groq_key
        endpoint = os.getenv("AI_BASE_URL", "").strip() or default_endpoint
        model = os.getenv("AI_MODEL", "").strip() or default_model
        auth_header = os.getenv("AI_AUTH_HEADER", "Authorization").strip()
        auth_scheme = os.getenv("AI_AUTH_SCHEME", "Bearer").strip()
        allow_no_auth = os.getenv("AI_ALLOW_NO_AUTH", "false").strip().lower() in ("1", "true", "yes")

        if not endpoint or not model or (not api_key and not allow_no_auth):
            logger.error("AI provider is not configured")
            self._send_json_response(500, {
                "error": "AI provider not configured. Add GROQ_API_KEY in Vercel, or configure AI_API_KEY, AI_BASE_URL and AI_MODEL for another provider."
            })
            return

        try:
            # Read and validate request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > MAX_REQUEST_SIZE:
                self._send_json_response(413, {"error": "Request body too large"})
                return
            if content_length == 0:
                self._send_json_response(400, {"error": "Empty request body"})
                return

            body = self.rfile.read(content_length)

            # Validate JSON payload
            try:
                request_data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json_response(400, {"error": "Invalid JSON in request body"})
                return

            request_data["model"] = model
            if provider == "groq" and model.startswith("openai/gpt-oss"):
                token_limit = request_data.pop("max_tokens", None)
                if token_limit is not None:
                    request_data["max_completion_tokens"] = token_limit
                request_data.setdefault("reasoning_effort", "low")
                request_data.setdefault("include_reasoning", False)
            body = json.dumps(request_data).encode("utf-8")
            logger.info("AI request: provider=%s model=%s", provider, model)

            # Forward request to the configured OpenAI-compatible API.
            req = urllib.request.Request(
                endpoint,
                data=body,
                method="POST"
            )
            req.add_header("Content-Type", "application/json")
            if api_key:
                req.add_header(auth_header, f"{auth_scheme} {api_key}".strip())
            req.add_header("User-Agent", "RoofGrid/1.0")

            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                result = resp.read()
                status = resp.getcode()

            logger.info("AI response: provider=%s status=%d", provider, status)

            self._send_json_response(status, json.loads(result))

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode('utf-8')
            except Exception:
                error_body = str(e)

            logger.error("AI provider HTTP %d: %s", e.code, error_body[:300])

            error_messages = {
                401: "The configured AI provider rejected AI_API_KEY.",
                403: "The configured AI provider forbids this key, model, or account.",
                429: "The configured AI provider rate limit was exceeded. Please wait and try again.",
            }
            message = error_messages.get(e.code)
            if not message:
                try:
                    upstream_error = json.loads(error_body)
                    error_value = upstream_error.get("error", upstream_error)
                    message = error_value.get("message") if isinstance(error_value, dict) else str(error_value)
                except (json.JSONDecodeError, TypeError, AttributeError):
                    message = "Upstream AI service error"

            self._send_json_response(e.code, {"error": message, "status": e.code})

        except urllib.error.URLError as e:
            logger.error("Network error contacting AI provider: %s", e.reason)
            self._send_json_response(502, {
                "error": "Network error when contacting AI service. Please try again."
            })

        except Exception as e:
            logger.exception("Unexpected error in AI handler")
            self._send_json_response(500, {
                "error": "Internal server error. Please try again later."
            })

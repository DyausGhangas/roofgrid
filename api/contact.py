from email.utils import parseaddr
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("roofgrid.contact")

MAX_REQUEST_SIZE = 16 * 1024
REQUEST_TIMEOUT = 15


class handler(BaseHTTPRequestHandler):
    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        recipient = os.getenv("CONTACT_EMAIL", "").strip()
        if not recipient or recipient.lower() == "you@example.com":
            self.send_json(503, {"error": "Contact delivery is not configured."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0 or content_length > MAX_REQUEST_SIZE:
                status = 413 if content_length > MAX_REQUEST_SIZE else 400
                self.send_json(status, {"error": "Invalid contact request size."})
                return

            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            sender = str(payload.get("email", "")).strip()
            subject = str(payload.get("_subject", payload.get("subject", ""))).strip()
            message = str(payload.get("message", "")).strip()
            honey = str(payload.get("_honey", payload.get("website", ""))).strip()

            parsed_email = parseaddr(sender)[1]
            valid_email = parsed_email == sender and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", sender)
            if honey:
                self.send_json(200, {"success": True})
                return
            if not valid_email or not 2 <= len(subject) <= 120 or not 10 <= len(message) <= 4000:
                self.send_json(400, {"error": "Enter a valid email, subject, and message."})
                return

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
            origin = self.headers.get("Origin", "")
            referer = self.headers.get("Referer", "")
            if origin.startswith(("https://", "http://")):
                request.add_header("Origin", origin)
            if referer.startswith(("https://", "http://")):
                request.add_header("Referer", referer)

            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                response_body = response.read()
                status = response.getcode()

            try:
                provider_result = json.loads(response_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                provider_result = {}

            provider_success = provider_result.get("success", True)
            if provider_success in (False, "false", 0, "0"):
                message = provider_result.get("message", "Contact service could not deliver the message.")
                self.send_json(502, {"success": False, "error": message})
            elif 200 <= status < 300:
                self.send_json(200, {
                    "success": True,
                    "message": provider_result.get("message", "Message accepted for delivery."),
                })
            else:
                self.send_json(502, {"error": "Contact service rejected the message."})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "Invalid contact request."})
        except urllib.error.HTTPError as error:
            logger.error("Contact service HTTP %d", error.code)
            self.send_json(502, {"error": "Contact service could not deliver the message."})
        except urllib.error.URLError as error:
            logger.error("Contact service network error: %s", error.reason)
            self.send_json(502, {"error": "Contact service is unavailable."})
        except Exception:
            logger.exception("Contact proxy error")
            self.send_json(500, {"error": "The message could not be sent."})

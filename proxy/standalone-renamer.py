#!/usr/bin/env python3
"""
Standalone model-renaming proxy for OpenWebUI.

Run this alongside your caveman-proxy container. Point one OpenWebUI connection
at this proxy (e.g. http://caveman-renamer:8789/v1) and the other at direct
OpenRouter. This proxy prefixes model names so OpenWebUI shows them distinctly,
and strips the prefix from outbound chat requests so OpenRouter accepts them.

Usage:
  OPENROUTER_API_KEY=sk-or-v1-xxx python3 standalone-renamer.py

Or via Docker:
  docker run -d --name caveman-renamer --network your-network \
    -e OPENROUTER_API_KEY=sk-or-v1-xxx \
    -e MODEL_PREFIX=cave- \
    -p 8789:8789 \
    python:3.12-slim python3 /path/to/standalone-renamer.py
"""
import os, json, http.server, urllib.request, urllib.error

LISTEN = os.environ.get("LISTEN", "0.0.0.0:8789").rsplit(":", 1)
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_BASE = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
MODEL_PREFIX = os.environ.get("MODEL_PREFIX", "cave-")


def strip_prefix(value):
    """Remove MODEL_PREFIX from a model id before forwarding to OpenRouter."""
    if MODEL_PREFIX and isinstance(value, str) and value.startswith(MODEL_PREFIX):
        return value[len(MODEL_PREFIX):]
    return value


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, code, msg):
        self._send_json(code, {"error": {"message": msg}})

    def _forward_headers(self):
        hdrs = {
            "Authorization": "Bearer " + OR_KEY,
            "Content-Type": "application/json",
        }
        if OR_KEY:
            hdrs["HTTP-Referer"] = "https://openwebui.local"
            hdrs["X-Title"] = "OpenWebUI"
        return hdrs

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        if "models" not in self.path:
            return self._send_error(404, "not found")
        req = urllib.request.Request(OR_BASE + "/models",
            headers=self._forward_headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            return self._send_error(e.code, e.read().decode())
        except Exception as e:
            return self._send_error(502, str(e))
        # Prefix all model IDs
        if "data" in data:
            for m in data["data"]:
                if "id" in m:
                    m["id"] = MODEL_PREFIX + m["id"]
        self._send_json(200, data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))

        # Strip the display prefix from the model field before forwarding,
        # so OpenRouter receives the REAL model id (it rejects 'cave-...').
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                if "model" in payload:
                    payload["model"] = strip_prefix(payload["model"])
                body = json.dumps(payload).encode()
        except (ValueError, TypeError):
            pass  # not JSON (or not a dict) -> forward unchanged

        # Check if client wants streaming
        is_stream = b'"stream":true' in body or b'"stream": True' in body
        path = self.path  # e.g. /v1/chat/completions
        url = OR_BASE.rstrip("/") + path
        hdrs = self._forward_headers()
        req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            return self._send_error(e.code, e.read().decode())
        except Exception as e:
            return self._send_error(502, str(e))

        if is_stream:
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ("content-length", "transfer-encoding"):
                    self.send_header(k, v)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except BrokenPipeError:
                    break
        else:
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ("content-length", "transfer-encoding"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    host, port = LISTEN[0], int(LISTEN[1])
    http.server.ThreadingHTTPServer((host, port), Proxy).serve_forever()

#!/usr/bin/env python3
"""Caveman proxy wrapper: GET /v1/models -> OpenRouter (renamed); POST /v1/chat/completions -> caveman-proxy with streaming support."""
import os, http.server, urllib.request, urllib.error, sys, json, select

LISTEN = os.environ.get("WRAPPER_LISTEN", "0.0.0.0:8787").rsplit(":", 1)
MODELS = os.environ.get("UPSTREAM_MODELS", "https://openrouter.ai/api/v1/models")
CHAT   = os.environ.get("CAVEMAN_UPSTREAM",
        "http://127.0.0.1:8788/compat/openrouter/v1/chat/completions")

# Prefix to distinguish caveman models from direct OpenRouter models in OpenWebUI
MODEL_PREFIX = os.environ.get("CAVEMAN_MODEL_PREFIX", "cave-")

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, code, body):
        body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, code, msg):
        self._send_json(code, {"error": {"message": msg, "type": "error"}})

    def _auth(self, req):
        if "Authorization" in self.headers:
            req.add_header("Authorization", self.headers["Authorization"])

    def do_OPTIONS(self):
        """Handle CORS preflight from OpenWebUI."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        path = self.path
        # /v1/models or /models -> fetch and rename models
        if "models" in path:
            req = urllib.request.Request(MODELS)
            self._auth(req)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
            except urllib.error.HTTPError as e:
                data = json.loads(e.read())
            except Exception as e:
                self._send_error_json(502, str(e))
                return

            # Rename models with prefix so OpenWebUI shows them distinctly
            if isinstance(data, dict) and "data" in data:
                for model in data["data"]:
                    if isinstance(model, dict) and "id" in model:
                        model["id"] = MODEL_PREFIX + model["id"]
            self._send_json(200, data)
        else:
            self._send_error_json(404, "not found")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))

        # Forward to caveman-proxy
        req = urllib.request.Request(CHAT, data=body, method="POST")
        for h in ("Content-Type", "Authorization", "Accept"):
            if h in self.headers:
                req.add_header(h, self.headers[h])

        # Check if client wants streaming
        is_stream = b'"stream":true' in body or b'"stream": True' in body

        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            self._send_error_json(e.code, e.read().decode("utf-8", errors="replace"))
            return
        except Exception as e:
            self._send_error_json(502, str(e))
            return

        if is_stream:
            # Streaming mode: forward SSE events chunk by chunk
            self.send_response(resp.status)
            for key, val in resp.headers.items():
                if key.lower() not in ("content-length", "transfer-encoding", "connection"):
                    self.send_header(key, val)
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
            # Non-streaming: forward the whole response
            data = resp.read()
            self.send_response(resp.status)
            for key, val in resp.headers.items():
                if key.lower() not in ("content-length", "transfer-encoding", "connection"):
                    self.send_header(key, val)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    host, port = LISTEN[0], int(LISTEN[1])
    http.server.ThreadingHTTPServer((host, port), H).serve_forever()

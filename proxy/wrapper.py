#!/usr/bin/env python3
"""Caveman proxy wrapper: GET /v1/models -> OpenRouter (renamed); POST /v1/chat/completions -> caveman-proxy with streaming support."""
import os, http.server, urllib.request, urllib.error, sys, json

LISTEN = os.environ.get("WRAPPER_LISTEN", "0.0.0.0:8787").rsplit(":", 1)
MODELS = os.environ.get("UPSTREAM_MODELS", "https://openrouter.ai/api/v1/models")
CHAT   = os.environ.get("CAVEMAN_UPSTREAM",
        "http://127.0.0.1:8788/compat/openrouter/v1/chat/completions")

# Prefix to distinguish caveman models from direct OpenRouter models in OpenWebUI
MODEL_PREFIX = os.environ.get("CAVEMAN_MODEL_PREFIX", "cave-")


def strip_prefix(value):
    """Remove MODEL_PREFIX from a model id (e.g. 'cave-~deepseek/x' -> '~deepseek/x')."""
    if MODEL_PREFIX and isinstance(value, str) and value.startswith(MODEL_PREFIX):
        return value[len(MODEL_PREFIX):]
    return value


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

            # Rename models with prefix so OpenWebUI shows them distinctly:
            #  - 'id'   -> prefixed (sent back to us in POST; we strip it then)
            #  - 'name' -> prefixed too, because mobile OpenWebUI shows the
            #              display name (not the id), so both connections
            #              looked identical without this.
            if isinstance(data, dict) and "data" in data:
                for model in data["data"]:
                    if not isinstance(model, dict):
                        continue
                    if "id" in model and isinstance(model["id"], str):
                        model["id"] = MODEL_PREFIX + model["id"]
                    # Display name must be prefixed too (mobile OpenWebUI shows
                    # 'name', not 'id'). Fall back to the prefixed id when the
                    # upstream omitted a name.
                    name = model.get("name")
                    if not isinstance(name, str) or name == "":
                        name = model.get("id", "")
                    if isinstance(name, str) and name != "":
                        if MODEL_PREFIX and not name.startswith(MODEL_PREFIX):
                            name = MODEL_PREFIX + name
                        model["name"] = name
            self._send_json(200, data)
        else:
            self._send_error_json(404, "not found")

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

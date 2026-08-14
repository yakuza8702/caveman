#!/usr/bin/env python3
"""Public wrapper: GET /models -> OpenRouter; POST /v1/chat/completions -> caveman-proxy loopback."""
import os, http.server, urllib.request, urllib.error, sys

LISTEN = os.environ.get("WRAPPER_LISTEN", "0.0.0.0:8787").rsplit(":",1)
MODELS = os.environ.get("UPSTREAM_MODELS", "https://openrouter.ai/api/v1/models")
CHAT   = os.environ.get("CAVEMAN_UPSTREAM",
        "http://127.0.0.1:8788/compat/openrouter/v1/chat/completions")

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def _auth(self, req):
        if "Authorization" in self.headers:
            req.add_header("Authorization", self.headers["Authorization"])
    def do_GET(self):
        if "models" in self.path:
            req = urllib.request.Request(MODELS); self._auth(req)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    self._send(r.status, r.read())
            except urllib.error.HTTPError as e:  self._send(e.code, e.read())
            except Exception as e:               self._send(502, ('{"error":{"message":"%s"}}'%e).encode())
        else:
            self._send(404, b'{"error":{"message":"not found"}}')
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        req = urllib.request.Request(CHAT, data=body, method="POST")
        for h in ("Content-Type", "Authorization"):
            if h in self.headers: req.add_header(h, self.headers[h])
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                self._send(r.status, r.read())
        except urllib.error.HTTPError as e:  self._send(e.code, e.read())
        except Exception as e:               self._send(502, ('{"error":{"message":"%s"}}'%e).encode())
    def log_message(self, *a): pass

if __name__ == "__main__":
    host, port = LISTEN[0], int(LISTEN[1])
    http.server.ThreadingHTTPServer((host, port), H).serve_forever()

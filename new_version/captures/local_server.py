"""local_server.py - serves the patched game directly over plain HTTP (no proxy involved).

Put it in the SAME folder as fake_server.py and your *.flow captures, then run:

    python local_server.py [--port 8090] [--public http://<YOUR-IP-ADDRESS>:8090]

It does not re-implement anything: every request is handed to fake_server.py (your
current copy, with all your fixes), so config, state, replies and file serving behave
exactly as they do through the proxy. This script only
  * receives plain HTTP requests from the patched game,
  * treats paths like /<package>/<uuid> as CDN downloads and everything else as the API,
  * rewrites the CDN links inside API replies so they point back at THIS server
    (links to anything else, e.g. promo images, are left alone).

--public is the address the game can reach this server at (what you gave --base).
Needs mitmproxy installed in the same Python (fake_server.py already needs it).
Stop with Ctrl+C.
"""
import argparse
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import msgpack

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_server as fs                                  # noqa: E402
from mitmproxy import http                                # noqa: E402
from mitmproxy.test import tflow                          # noqa: E402

CDN_PREFIX = f"https://{fs.CDN_HOST}/{fs.PKG}/"
PUBLIC = ""


def rewrite(o):
    """Point recorded CDN links at this server (walks the decoded msgpack reply)."""
    if isinstance(o, str):
        return PUBLIC + "/" + fs.PKG + "/" + o[len(CDN_PREFIX):] if o.startswith(CDN_PREFIX) else o
    if isinstance(o, list):
        return [rewrite(x) for x in o]
    if isinstance(o, dict):
        return {k: rewrite(v) for k, v in o.items()}
    return o


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"          # keep-alive, like the real server

    def _send(self, code, body=b"", ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        path = self.path
        if path in ("/", ""):
            return self._send(200, b"local server running\n")
        is_cdn = path.startswith(f"/{fs.PKG}/")
        host = fs.CDN_HOST if is_cdn else fs.API_HOST
        headers = [(b"content-type", (self.headers.get("Content-Type") or "").encode())]
        fl = tflow.tflow()
        fl.request = http.Request.make(self.command, f"https://{host}{path}", body, http.Headers(headers))
        fl.response = None
        fs.request(fl)                       # all the real logic lives in fake_server.py
        r = fl.response
        if r is None:
            print(f"[local] nothing answered {self.command} {path}")
            return self._send(404)
        content = r.content or b""
        if not is_cdn and path.startswith("/api"):
            try:
                content = msgpack.packb(rewrite(msgpack.unpackb(content, raw=False, strict_map_key=False)),
                                        use_bin_type=True)
            except Exception as e:
                print("[local] could not rewrite links:", e)
        self._send(r.status_code, content, r.headers.get("content-type", "application/octet-stream"))

    do_GET = do_POST = do_HEAD = _handle

    def log_message(self, fmt, *args):       # fake_server already prints one line per call
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--public", default="", help="address the game uses to reach this server")
    a = ap.parse_args()
    PUBLIC = (a.public or f"http://127.0.0.1:{a.port}").rstrip("/")
    fs._ensure_loaded()
    print(f"[local] listening on 0.0.0.0:{a.port}; CDN links will point at {PUBLIC}")
    try:
        ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n[local] stopped")

"""Serwer HTTP (tylko biblioteka standardowa). Treści rozmów nie trafiają do logów."""
import hmac
import json
import logging
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config, db, engine, push

log = logging.getLogger("znajomy")
_rate = {}


def _limited(key, n, per):
    now = time.time()
    hits = [t for t in _rate.get(key, []) if now - t < per]
    if len(hits) >= n:
        _rate[key] = hits
        return True
    hits.append(now)
    _rate[key] = hits
    return False


class Handler(BaseHTTPRequestHandler):
    server_version = "Znajomy"

    def log_message(self, fmt, *args):   # bez adresów i treści w logach
        pass

    # --- pomocnicze
    def _cors(self):
        if config.ORIGIN:
            self.send_header("Access-Control-Allow-Origin", config.ORIGIN)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000:
            return None
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return None

    def _uid(self):
        h = self.headers.get("Authorization", "")
        return engine.user_by_token(h[7:] if h.startswith("Bearer ") else "")

    # --- metody
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/api/health":
            return self._json(200, {"ok": True})
        if p == "/api/messages":
            uid = self._uid()
            if not uid:
                return self._json(401, {"error": "auth"})
            after = int((parse_qs(u.query).get("after") or ["0"])[0] or 0)
            reads = [r["id"] for r in db.q(
                "SELECT id FROM messages WHERE user_id=? AND role='user' AND read_ts IS NOT NULL ORDER BY id DESC LIMIT 30", (uid,))]
            return self._json(200, {"messages": engine.visible_messages(uid, after),
                                    "presence": engine.presence(uid), "read_ids": reads})
        if p == "/api/push/key":
            return self._json(200, {"key": push.public_key()})
        return self._static(p)

    def do_POST(self):
        p = urlparse(self.path).path
        b = self._body()
        if b is None:
            return self._json(400, {"error": "zły format"})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0])
        if p == "/api/register":
            if _limited("reg:" + ip, 8, 600):
                return self._json(429, {"error": "za często"})
            code = str(b.get("code", ""))
            ok = config.DEV or any(hmac.compare_digest(code, c) for c in config.CODES)
            if not ok:
                return self._json(403, {"error": "zły kod dostępu"})
            if not b.get("adult") or not b.get("ack_ai"):
                return self._json(400, {"error": "wymagane potwierdzenia"})
            uid, token = engine.create_user(True)
            return self._json(200, {"token": token})
        uid = self._uid()
        if not uid:
            return self._json(401, {"error": "auth"})
        if p == "/api/send":
            if _limited("send:%s" % uid, 40, 60):
                return self._json(429, {"error": "za często"})
            mid = engine.handle_user_message(uid, str(b.get("text", "")))
            return self._json(200, {"id": mid})
        if p == "/api/forget":
            engine.forget(uid)
            return self._json(200, {"ok": True})
        if p == "/api/push/subscribe":
            return self._json(200, {"ok": push.subscribe(uid, b.get("subscription"))})
        return self._json(404, {"error": "brak"})

    def _static(self, p):
        if p in ("", "/"):
            p = "/index.html"
        f = (config.WEB_DIR / p.lstrip("/")).resolve()
        if config.WEB_DIR.resolve() not in f.parents or not f.is_file():
            self.send_response(404)
            self.end_headers()
            return
        data = f.read_bytes()
        ct = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ct + ("; charset=utf-8" if ct.startswith("text/") or "javascript" in ct else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def _loop():
    while True:
        try:
            engine.tick()
        except Exception:
            log.exception("tick")
        time.sleep(config.TICK)


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.init()
    threading.Thread(target=_loop, daemon=True).start()
    srv = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    log.info("Znajomy działa na %s:%s (LLM=%s)", config.HOST, config.PORT, config.LLM)
    srv.serve_forever()

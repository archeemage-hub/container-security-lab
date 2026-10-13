import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROLE = os.environ.get("APP_ROLE", "store")
PORT = int(os.environ.get("PORT", "8080"))
TOKEN_FILE = Path(os.environ.get("TOKEN_FILE", "/run/secrets/backend-token"))
STORE_URL = os.environ.get("STORE_URL", "http://store:8080")
DATA_FILE = Path(os.environ.get("DATA_FILE", "/data/notes.json"))
LOCK = threading.Lock()


def read_token():
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def load_notes():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


class Handler(BaseHTTPRequestHandler):
    server_version = "NotesLab/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def respond(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)
        print(json.dumps({"role": ROLE, "method": self.command, "path": self.path,
                          "status": status, "time": round(time.time(), 3)}), flush=True)

    def do_GET(self):
        if self.path in ("/health", "/ready"):
            return self.respond(200, {"status": "ok", "role": ROLE})
        if self.path != "/notes":
            return self.respond(404, {"error": "not_found"})
        if ROLE == "gateway":
            return self.forward()
        if not self.authorized():
            return self.respond(401, {"error": "unauthorized"})
        with LOCK:
            notes = load_notes()
        self.respond(200, {"notes": notes, "count": len(notes)})

    def do_POST(self):
        if self.path != "/notes":
            return self.respond(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.respond(400, {"error": "bad_length"})
        if length < 1 or length > 4096:
            return self.respond(413, {"error": "body_limit"})
        raw = self.rfile.read(length)
        if ROLE == "gateway":
            return self.forward(raw)
        if not self.authorized():
            return self.respond(401, {"error": "unauthorized"})
        try:
            value = json.loads(raw)
            text = value["text"]
            if not isinstance(text, str) or not 1 <= len(text) <= 160:
                raise ValueError("text_length")
        except (ValueError, TypeError, KeyError):
            return self.respond(400, {"error": "invalid_note"})
        with LOCK:
            notes = load_notes()
            if len(notes) >= 100:
                return self.respond(409, {"error": "notes_limit"})
            note = {"id": len(notes) + 1, "text": text}
            notes.append(note)
            temporary = DATA_FILE.with_suffix(".tmp")
            temporary.write_text(json.dumps(notes, ensure_ascii=False), encoding="utf-8")
            temporary.replace(DATA_FILE)
        self.respond(201, note)

    def authorized(self):
        try:
            expected = "Bearer " + read_token()
        except OSError:
            return False
        actual = self.headers.get("Authorization", "")
        return hmac.compare_digest(actual.encode("utf-8"), expected.encode("utf-8"))

    def forward(self, raw=None):
        try:
            req = urllib.request.Request(STORE_URL + "/notes", data=raw,
                headers={"Authorization": "Bearer " + read_token(),
                         "Content-Type": "application/json"}, method=self.command)
            with urllib.request.urlopen(req, timeout=3) as response:
                payload = json.loads(response.read(131072))
                self.respond(response.status, payload)
        except urllib.error.HTTPError as error:
            self.respond(error.code, {"error": "upstream_rejected"})
        except (OSError, ValueError):
            self.respond(503, {"error": "store_unavailable"})


if __name__ == "__main__":
    if ROLE == "store":
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

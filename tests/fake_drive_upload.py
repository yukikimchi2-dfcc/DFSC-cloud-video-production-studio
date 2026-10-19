"""A local fake of Drive's resumable-upload endpoint (protocol subset) for offline tests.

Implements: session start (POST ...uploadType=resumable), chunk PUTs with Content-Range,
status queries (Content-Range: bytes */total), 308 + Range progress, final 200 with metadata incl.
md5Checksum, optional injected 503s and session expiry. Not Google — only proves our client logic.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeDrive:
    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.files: dict[str, dict] = {}
        self.fail_puts: set[int] = set()      # 1-based PUT numbers that answer 503
        self.put_count = 0
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()

    def expire_all(self):
        self.sessions.clear()

    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code, headers=None, body=b""):
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                meta = json.loads(body or b"{}")
                sid = uuid.uuid4().hex
                fake.sessions[sid] = {"meta": meta, "total": int(self.headers["X-Upload-Content-Length"]),
                                      "mime": self.headers.get("X-Upload-Content-Type"), "data": bytearray()}
                self._send(200, {"Location": f"{fake.base_url}/upload/session/{sid}"})

            def do_PUT(self):
                sid = self.path.rsplit("/", 1)[-1]
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                s = fake.sessions.get(sid)
                if s is None:
                    return self._send(404)
                cr = self.headers["Content-Range"]               # "bytes a-b/total" or "bytes */total"
                rng, total = cr.split(" ", 1)[1].split("/")
                with fake.lock:
                    if rng != "*":
                        fake.put_count += 1
                        if fake.put_count in fake.fail_puts:
                            return self._send(503)
                        start, end = (int(x) for x in rng.split("-"))
                        if start == len(s["data"]) and end - start + 1 == len(body):
                            s["data"] += body
                    have = len(s["data"])
                if have == s["total"]:
                    fid = "fake_" + sid[:12]
                    md = {"id": fid, "name": s["meta"].get("name"), "mimeType": s["mime"],
                          "parents": s["meta"].get("parents", []), "size": str(have),
                          "md5Checksum": hashlib.md5(s["data"]).hexdigest()}
                    fake.files[fid] = {**md, "data": bytes(s["data"])}
                    return self._send(200, {"Content-Type": "application/json"}, json.dumps(md).encode())
                headers = {"Range": f"bytes=0-{have - 1}"} if have else {}
                self._send(308, headers)

        return H

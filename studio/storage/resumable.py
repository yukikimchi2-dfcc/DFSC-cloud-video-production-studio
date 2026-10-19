"""Google Drive resumable upload (protocol level) that survives process restarts.

Why not googleapiclient's MediaFileUpload: its session URI lives only in memory, so a crash or a
container recycle restarts a 30 MB render from byte 0. Here the session URI is persisted to a small
state file; on the next run we ask Drive how many bytes it already has and continue from there.

Protocol (https://developers.google.com/workspace/drive/api/guides/manage-uploads#resumable):
  POST  /upload/drive/v3/files?uploadType=resumable   -> 200, Location: <session URI>
  PUT   <session URI>  Content-Range: bytes a-b/total -> 308 (Range: bytes=0-b) ... 200/201 + metadata
  PUT   <session URI>  Content-Range: bytes */total   -> status query (308 with Range, or 200/201 done)
  404/410 on the session URI means it expired (sessions live about a week) -> start a new one.

`session` is any requests-compatible object: google.auth.transport.requests.AuthorizedSession in
production (adds and refreshes the OAuth token), a plain requests.Session against a fake in tests.
Only one chunk (default 8 MiB, a multiple of 256 KiB as Drive requires) is held in memory.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import time
from pathlib import Path

DRIVE_UPLOAD_BASE = "https://www.googleapis.com"
FIELDS = "id,name,mimeType,parents,size,md5Checksum,modifiedTime,version,webViewLink"
CHUNK = 8 * 1024 * 1024
_QUANTUM = 256 * 1024


class UploadError(RuntimeError):
    pass


def _state_key(local: Path, parent_id: str, name: str) -> str:
    st = local.stat()
    raw = f"{local.resolve()}|{st.st_size}|{int(st.st_mtime)}|{parent_id}|{name}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _next_offset(resp) -> int:
    """Byte offset to send next, from a 308 response's Range header (absent = nothing stored yet)."""
    rng = resp.headers.get("Range")
    return int(rng.rsplit("-", 1)[1]) + 1 if rng else 0


class ResumableUploader:
    def __init__(self, session, state_dir: str | Path, base_url: str = DRIVE_UPLOAD_BASE,
                 chunk_size: int = CHUNK, retries: int = 6, backoff: float = 1.0, log=None):
        if chunk_size % _QUANTUM:
            raise ValueError("chunk_size must be a multiple of 256 KiB (Drive requirement)")
        self.session, self.base_url = session, base_url.rstrip("/")
        self.state_dir = Path(state_dir)
        self.chunk_size, self.retries, self.backoff = chunk_size, retries, backoff
        self.log = log or (lambda msg: None)

    # ---------------------------------------------------------------- state
    def _state_path(self, key: str) -> Path:
        return self.state_dir / f"{key}.json"

    def _load(self, key: str) -> dict | None:
        p = self._state_path(key)
        return json.loads(p.read_text()) if p.exists() else None

    def _save(self, key: str, state: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(self._state_path(key))

    # ---------------------------------------------------------------- protocol
    def _start(self, local: Path, parent_id: str, name: str, mime: str, total: int) -> str:
        r = self.session.post(
            f"{self.base_url}/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true&fields={FIELDS}",
            json={"name": name, "parents": [parent_id]},
            headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(total)}, timeout=60)
        if r.status_code != 200 or "Location" not in r.headers:
            raise UploadError(f"could not start resumable session: HTTP {r.status_code} {r.text[:200]}")
        return r.headers["Location"]

    def _query(self, uri: str, total: int):
        return self.session.put(uri, headers={"Content-Range": f"bytes */{total}", "Content-Length": "0"},
                                data=b"", timeout=60)

    def upload(self, local: str | Path, parent_id: str, name: str | None = None,
               mime_type: str | None = None, stop_after_chunks: int | None = None) -> dict:
        """Upload `local` into folder `parent_id`; returns Drive file metadata (dict).

        `stop_after_chunks` simulates a crash after N chunks (tests / acceptance runs): the session
        URI stays on disk and the next call resumes.
        """
        local = Path(local)
        name = name or local.name
        mime = mime_type or mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        total = local.stat().st_size
        key = _state_key(local, parent_id, name)
        state = self._load(key)
        offset = 0
        if state:
            r = self._query(state["session_uri"], total)
            if r.status_code in (200, 201):
                self._state_path(key).unlink(missing_ok=True)
                return r.json()
            if r.status_code == 308:
                offset = _next_offset(r)
                self.log(f"resuming {name} at byte {offset}/{total}")
            else:  # 404/410: session expired or unknown -> start over
                self.log(f"stored session invalid (HTTP {r.status_code}); starting a new one")
                state = None
        if not state:
            state = {"session_uri": self._start(local, parent_id, name, mime, total), "file": str(local),
                     "parent": parent_id, "name": name, "total": total, "started": time.time()}
            self._save(key, state)
        uri, sent_chunks, failures = state["session_uri"], 0, 0
        with open(local, "rb") as f:
            while True:
                if stop_after_chunks is not None and sent_chunks >= stop_after_chunks:
                    raise UploadError(f"simulated interruption after {sent_chunks} chunks at byte {offset}")
                f.seek(offset)
                data = f.read(self.chunk_size)
                end = offset + len(data) - 1
                try:
                    r = self.session.put(uri, data=data, timeout=300, headers={
                        "Content-Length": str(len(data)), "Content-Range": f"bytes {offset}-{end}/{total}"})
                except Exception as e:  # noqa: BLE001 — network drop mid-chunk: ask Drive where we are
                    r, err = None, e
                if r is not None and r.status_code in (200, 201):
                    self._state_path(key).unlink(missing_ok=True)
                    return r.json()
                if r is not None and r.status_code == 308:
                    offset, sent_chunks, failures = _next_offset(r), sent_chunks + 1, 0
                    state["offset"] = offset
                    self._save(key, state)
                    continue
                if r is not None and r.status_code in (404, 410):
                    self._state_path(key).unlink(missing_ok=True)
                    raise UploadError("upload session expired; re-run to start a new session")
                failures += 1
                if failures > self.retries:
                    detail = f"HTTP {r.status_code} {r.text[:200]}" if r is not None else repr(err)
                    raise UploadError(f"chunk at byte {offset} failed {failures} times: {detail}")
                time.sleep(min(self.backoff * 2 ** failures, 60))
                q = self._query(uri, total)
                if q.status_code in (200, 201):
                    self._state_path(key).unlink(missing_ok=True)
                    return q.json()
                if q.status_code == 308:
                    offset = _next_offset(q)

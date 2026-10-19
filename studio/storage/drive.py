"""Google Drive implementation of the Store interface (Drive API v3).

Auth (first match wins):
  1. STUDIO_DRIVE_CREDENTIALS / GOOGLE_APPLICATION_CREDENTIALS -> service-account JSON.
     Share the team folders with the service account's e-mail (Editor) — it sees nothing else.
  2. STUDIO_DRIVE_TOKEN -> authorised-user token JSON (OAuth, acting as a team member).
Credential files live outside git (see .gitignore: secrets/, *.service-account.json, token*.json).

Transfers are chunked and resumable: uploads use Drive resumable sessions; downloads use HTTP
Range requests appending to <file>.partial, so an interrupted download continues where it stopped.
Every transfer is checked against Drive's md5Checksum.
"""
from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path
from typing import Iterator

from .base import FOLDER_MIME, IntegrityError, RemoteFile, verify

SCOPES = ["https://www.googleapis.com/auth/drive"]
FIELDS = "id,name,mimeType,parents,size,md5Checksum,modifiedTime,version,webViewLink"
CHUNK = 8 * 1024 * 1024


class DriveUnavailableError(RuntimeError):
    pass


def _credentials():
    try:
        from google.oauth2 import credentials as user_creds
        from google.oauth2 import service_account
    except ImportError as e:  # pragma: no cover
        raise DriveUnavailableError("pip install google-api-python-client google-auth") from e
    sa = os.environ.get("STUDIO_DRIVE_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if sa and Path(sa).exists():
        return service_account.Credentials.from_service_account_file(sa, scopes=SCOPES)
    token = os.environ.get("STUDIO_DRIVE_TOKEN")
    if token and Path(token).exists():
        return user_creds.Credentials.from_authorized_user_file(token, SCOPES)
    raise DriveUnavailableError(
        "No Google Drive credentials in this runtime. Set STUDIO_DRIVE_TOKEN to an OAuth token file or "
        "STUDIO_DRIVE_CREDENTIALS to a service-account JSON path (folders shared as anyone:writer need no "
        "extra sharing; private folders must be shared with that identity). "
        "See docs/zh/03_Google_Drive_连接.md")


def _to_remote(d: dict) -> RemoteFile:
    return RemoteFile(id=d["id"], name=d["name"], mime_type=d["mimeType"], parents=d.get("parents", []),
                      size=int(d["size"]) if d.get("size") else None, md5=d.get("md5Checksum"),
                      modified=d.get("modifiedTime"), version=d.get("version"), web_link=d.get("webViewLink"))


def _q_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


class DriveStore:
    name = "gdrive"

    def __init__(self, credentials=None, retries: int = 5):
        from googleapiclient.discovery import build
        self.creds = credentials or _credentials()
        self.service = build("drive", "v3", credentials=self.creds, cache_discovery=False)
        self.retries = retries

    def _exec(self, request):
        return request.execute(num_retries=self.retries)

    def about(self) -> dict:
        return self._exec(self.service.about().get(fields="user(emailAddress,displayName),storageQuota"))

    def get(self, file_id: str) -> RemoteFile:
        return _to_remote(self._exec(self.service.files().get(fileId=file_id, fields=FIELDS, supportsAllDrives=True)))

    def list_children(self, folder_id: str, page_size: int = 200) -> Iterator[RemoteFile]:
        token = None
        while True:
            resp = self._exec(self.service.files().list(
                q=f"'{folder_id}' in parents and trashed = false", fields=f"nextPageToken,files({FIELDS})",
                pageSize=page_size, pageToken=token, supportsAllDrives=True, includeItemsFromAllDrives=True,
                orderBy="folder,name"))
            for d in resp.get("files", []):
                yield _to_remote(d)
            token = resp.get("nextPageToken")
            if not token:
                return

    def find_child(self, parent_id: str, name: str, folder: bool | None = None) -> RemoteFile | None:
        q = f"'{parent_id}' in parents and name = '{_q_escape(name)}' and trashed = false"
        if folder is True:
            q += f" and mimeType = '{FOLDER_MIME}'"
        elif folder is False:
            q += f" and mimeType != '{FOLDER_MIME}'"
        resp = self._exec(self.service.files().list(q=q, fields=f"files({FIELDS})", pageSize=10,
                                                    supportsAllDrives=True, includeItemsFromAllDrives=True))
        files = resp.get("files", [])
        return _to_remote(files[0]) if files else None

    def create_folder(self, parent_id: str, name: str) -> RemoteFile:
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        return _to_remote(self._exec(self.service.files().create(body=body, fields=FIELDS, supportsAllDrives=True)))

    def upload(self, local, parent_id, name=None, mime_type=None) -> RemoteFile:
        from googleapiclient.http import MediaFileUpload
        local = Path(local)
        mime_type = mime_type or mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        media = MediaFileUpload(str(local), mimetype=mime_type, chunksize=CHUNK, resumable=True)
        req = self.service.files().create(body={"name": name or local.name, "parents": [parent_id]},
                                          media_body=media, fields=FIELDS, supportsAllDrives=True)
        resp = None
        while resp is None:
            _, resp = req.next_chunk(num_retries=self.retries)
        remote = _to_remote(resp)
        verify(local, remote)
        return remote

    def download(self, file_id: str, local) -> Path:
        from google.auth.transport.requests import AuthorizedSession
        meta = self.get(file_id)
        if meta.mime_type.startswith("application/vnd.google-apps"):
            raise ValueError(f"{meta.name} is a Google-native document; export it instead of downloading")
        local = Path(local)
        local.parent.mkdir(parents=True, exist_ok=True)
        part = local.with_name(local.name + ".partial")
        session = AuthorizedSession(self.creds)
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
        total = meta.size or 0
        attempt = 0
        while True:
            have = part.stat().st_size if part.exists() else 0
            if total and have >= total:
                break
            end = min(have + CHUNK, total) - 1 if total else ""
            try:
                r = session.get(url, headers={"Range": f"bytes={have}-{end}"}, timeout=120)
                if r.status_code not in (200, 206):
                    r.raise_for_status()
                with open(part, "ab" if r.status_code == 206 else "wb") as f:
                    f.write(r.content)
                attempt = 0
                if not total:
                    break
            except Exception:  # noqa: BLE001 — network hiccup: back off and resume from the .partial
                attempt += 1
                if attempt > self.retries:
                    raise
                time.sleep(min(2 ** attempt, 30))
        part.replace(local)
        try:
            verify(local, meta)
        except IntegrityError:
            local.rename(local.with_name(local.name + ".corrupt"))
            raise
        return local

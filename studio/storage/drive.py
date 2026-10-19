"""Google Drive implementation of the Store interface (Drive API v3).

Auth (first match wins) — values come from the cloud environment's secrets, never from git or chat:
  1. STUDIO_DRIVE_OAUTH_CLIENT_ID + STUDIO_DRIVE_OAUTH_CLIENT_SECRET + STUDIO_DRIVE_OAUTH_REFRESH_TOKEN
     -> OAuth user credentials (recommended for a personal Gmail: files count against that user's
        quota). Produced once by tools/drive_oauth_bootstrap.py; see docs/zh/04_Drive_OAuth_自动上传.md.
  2. STUDIO_DRIVE_TOKEN -> path to an authorised-user token JSON (same thing, as a file).
  3. STUDIO_DRIVE_CREDENTIALS / GOOGLE_APPLICATION_CREDENTIALS -> service-account JSON.
     Only useful with a Workspace shared drive: service accounts have no storage quota of their own.

Transfers: uploads use studio.storage.resumable (Drive resumable protocol, chunked, session URI
persisted so a crash resumes instead of restarting); downloads stream HTTP Range chunks into
<file>.partial. Every transfer is checked against Drive's md5Checksum.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterator

from .base import FOLDER_MIME, IntegrityError, RemoteFile, verify

# Full drive scope is needed to write into the existing output folder (created by another app).
# drive.file works only for a tree this client creates itself — set STUDIO_DRIVE_OAUTH_SCOPE to opt in.
SCOPES = [os.environ.get("STUDIO_DRIVE_OAUTH_SCOPE", "https://www.googleapis.com/auth/drive")]
FIELDS = "id,name,mimeType,parents,size,md5Checksum,modifiedTime,version,webViewLink"
CHUNK = 8 * 1024 * 1024


class DriveUnavailableError(RuntimeError):
    pass


TOKEN_URI = "https://oauth2.googleapis.com/token"
OAUTH_ENV = ("STUDIO_DRIVE_OAUTH_CLIENT_ID", "STUDIO_DRIVE_OAUTH_CLIENT_SECRET", "STUDIO_DRIVE_OAUTH_REFRESH_TOKEN")


def credential_source() -> str | None:
    """Which credential source is configured (names only — never values)."""
    if all(os.environ.get(k) for k in OAUTH_ENV):
        return "oauth_env"
    if os.environ.get("STUDIO_DRIVE_TOKEN") and Path(os.environ["STUDIO_DRIVE_TOKEN"]).exists():
        return "oauth_token_file"
    sa = os.environ.get("STUDIO_DRIVE_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if sa and Path(sa).exists():
        return "service_account"
    return None


def _credentials():
    try:
        from google.oauth2 import credentials as user_creds
        from google.oauth2 import service_account
    except ImportError as e:  # pragma: no cover
        raise DriveUnavailableError("pip install google-api-python-client google-auth") from e
    source = credential_source()
    if source == "oauth_env":
        cid, secret, refresh = (os.environ[k] for k in OAUTH_ENV)
        return user_creds.Credentials(token=None, refresh_token=refresh, client_id=cid, client_secret=secret,
                                      token_uri=TOKEN_URI, scopes=SCOPES)
    if source == "oauth_token_file":
        return user_creds.Credentials.from_authorized_user_file(os.environ["STUDIO_DRIVE_TOKEN"], SCOPES)
    if source == "service_account":
        sa = os.environ.get("STUDIO_DRIVE_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        return service_account.Credentials.from_service_account_file(sa, scopes=SCOPES)
    missing = [k for k in OAUTH_ENV if not os.environ.get(k)]
    raise DriveUnavailableError(
        "No Google Drive credentials in this runtime (missing env secrets: " + ", ".join(missing) + "). "
        "Run tools/drive_oauth_bootstrap.py once and store its three values as environment secrets. "
        "See docs/zh/04_Drive_OAuth_自动上传.md")


def _to_remote(d: dict) -> RemoteFile:
    return RemoteFile(id=d["id"], name=d["name"], mime_type=d["mimeType"], parents=d.get("parents", []),
                      size=int(d["size"]) if d.get("size") else None, md5=d.get("md5Checksum"),
                      modified=d.get("modifiedTime"), version=d.get("version"), web_link=d.get("webViewLink"))


def _q_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


class DriveStore:
    name = "gdrive"

    def __init__(self, credentials=None, retries: int = 5, state_dir: str | Path | None = None):
        from googleapiclient.discovery import build
        self.creds = credentials or _credentials()
        self.service = build("drive", "v3", credentials=self.creds, cache_discovery=False)
        self.retries = retries
        if state_dir is None:
            from ..config import REPO_ROOT
            state_dir = REPO_ROOT / "workspace" / "uploads"
        self.state_dir = Path(state_dir)

    def _session(self):
        from google.auth.transport.requests import AuthorizedSession
        return AuthorizedSession(self.creds)

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

    def upload(self, local, parent_id, name=None, mime_type=None, stop_after_chunks=None, log=None) -> RemoteFile:
        from .resumable import ResumableUploader
        local = Path(local)
        uploader = ResumableUploader(self._session(), self.state_dir, retries=self.retries, log=log)
        remote = _to_remote(uploader.upload(local, parent_id, name, mime_type, stop_after_chunks=stop_after_chunks))
        verify(local, remote)
        return remote

    def download(self, file_id: str, local) -> Path:
        meta = self.get(file_id)
        if meta.mime_type.startswith("application/vnd.google-apps"):
            raise ValueError(f"{meta.name} is a Google-native document; export it instead of downloading")
        local = Path(local)
        local.parent.mkdir(parents=True, exist_ok=True)
        part = local.with_name(local.name + ".partial")
        session = self._session()
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
        total = meta.size or 0
        attempt = 0
        while True:
            have = part.stat().st_size if part.exists() else 0
            if total and have >= total:
                break
            end = min(have + CHUNK, total) - 1 if total else ""
            try:
                r = session.get(url, headers={"Range": f"bytes={have}-{end}"}, timeout=120, stream=True)
                if r.status_code not in (200, 206):
                    r.raise_for_status()
                with open(part, "ab" if r.status_code == 206 else "wb") as f:
                    for block in r.iter_content(1 << 20):   # stream to disk, never hold the chunk twice
                        f.write(block)
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

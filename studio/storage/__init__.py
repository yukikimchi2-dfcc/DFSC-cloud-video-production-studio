"""Storage backends. `get_store()` picks Google Drive when credentials are configured."""
from __future__ import annotations

import os
from pathlib import Path

from .base import STUDIO_STRUCTURE, IntegrityError, RemoteFile, Store, ensure_structure, md5_file, walk  # noqa: F401
from .local import LocalStore


def get_store(kind: str | None = None, local_root: str | Path | None = None) -> Store:
    kind = kind or os.environ.get("STUDIO_STORE") or "gdrive"
    if kind == "local":
        from ..config import REPO_ROOT
        return LocalStore(local_root or os.environ.get("STUDIO_LOCAL_STORE") or REPO_ROOT / "workspace" / "local_store")
    if kind == "gdrive":
        from .drive import DriveStore
        return DriveStore()
    raise ValueError(f"unknown store '{kind}' (use gdrive or local)")

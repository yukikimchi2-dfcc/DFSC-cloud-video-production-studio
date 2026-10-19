"""Filesystem implementation of the Store interface.

Used for tests, for offline work, and as the cloud scratch workspace mirror. File ids are
paths relative to the store root ("" = root).
"""
from __future__ import annotations

import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .base import FOLDER_MIME, RemoteFile, md5_file, verify


class LocalStore:
    name = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _abs(self, file_id: str) -> Path:
        p = (self.root / file_id).resolve()
        if self.root.resolve() not in (p, *p.parents):
            raise ValueError(f"id escapes store root: {file_id}")
        return p

    def _meta(self, p: Path) -> RemoteFile:
        rel = "" if p == self.root.resolve() else str(p.relative_to(self.root.resolve()))
        parent = str(Path(rel).parent) if rel else ""
        stat = p.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
        if p.is_dir():
            return RemoteFile(rel, p.name, FOLDER_MIME, [parent if parent != "." else ""], modified=modified)
        return RemoteFile(rel, p.name, mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                          [parent if parent != "." else ""], size=stat.st_size, md5=md5_file(p), modified=modified)

    def get(self, file_id: str) -> RemoteFile:
        return self._meta(self._abs(file_id))

    def list_children(self, folder_id: str, page_size: int = 200) -> Iterator[RemoteFile]:
        for p in sorted(self._abs(folder_id).iterdir()):
            if not p.name.endswith(".partial"):
                yield self._meta(p)

    def find_child(self, parent_id: str, name: str, folder: bool | None = None) -> RemoteFile | None:
        p = self._abs(parent_id) / name
        if not p.exists() or (folder is True and not p.is_dir()) or (folder is False and p.is_dir()):
            return None
        return self._meta(p.resolve())

    def create_folder(self, parent_id: str, name: str) -> RemoteFile:
        p = self._abs(parent_id) / name
        p.mkdir(parents=False, exist_ok=False)
        return self._meta(p.resolve())

    def upload(self, local, parent_id, name=None, mime_type=None) -> RemoteFile:
        dest = self._abs(parent_id) / (name or Path(local).name)
        if dest.exists():
            # keep history instead of overwriting: name (2).ext, name (3).ext ...
            stem, suffix, n = dest.stem, dest.suffix, 2
            while dest.exists():
                dest = dest.with_name(f"{stem} ({n}){suffix}")
                n += 1
        tmp = dest.with_name(dest.name + ".partial")
        shutil.copyfile(local, tmp)
        tmp.replace(dest)
        meta = self._meta(dest.resolve())
        verify(local, meta)
        return meta

    def download(self, file_id: str, local) -> Path:
        src = self._abs(file_id)
        local = Path(local)
        local.parent.mkdir(parents=True, exist_ok=True)
        tmp = local.with_name(local.name + ".partial")
        shutil.copyfile(src, tmp)
        tmp.replace(local)
        verify(local, self._meta(src))
        return local

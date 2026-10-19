"""Storage interface shared by Google Drive and the local filesystem backend.

Rules every backend and every caller must follow (team policy, see docs/zh/):
  * never delete or move a user's file — only create folders, add files, and add new versions
  * folders are found-or-created by name, so re-running setup never duplicates them
  * every transfer is verified against an MD5 checksum
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Protocol

FOLDER_MIME = "application/vnd.google-apps.folder"

STUDIO_ROOT_NAME = "Cloud Video Production Studio"
STUDIO_STRUCTURE: dict[str, list[str]] = {
    "01_Brand_Library": ["Brand_Guidelines", "Logos", "Fonts", "Color_Palettes", "Brand_Assets"],
    "02_Source_Materials": ["Raw_Videos", "Interviews", "Photos", "Product_Images", "Audio", "Music"],
    "03_Style_References": ["Previous_Edits", "Approved_Videos", "Motion_References", "Editing_References",
                            "Visual_References"],
    "04_Motion_Graphics_Library": ["Typography", "Title_Cards", "Transitions", "Stickers", "Particles",
                                   "Lower_Thirds", "Outro_Templates"],
    "05_Active_Projects": [],
    "06_Project_Previews": [],
    "07_Approved_Final_Videos": [],
    "08_QC_Reports": [],
    "09_Archive": [],
    "10_Team_Documentation": [],
}


@dataclass
class RemoteFile:
    id: str
    name: str
    mime_type: str
    parents: list[str] = field(default_factory=list)
    size: int | None = None
    md5: str | None = None
    modified: str | None = None
    version: str | None = None
    web_link: str | None = None

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME


class Store(Protocol):
    name: str

    def get(self, file_id: str) -> RemoteFile: ...
    def list_children(self, folder_id: str, page_size: int = 200) -> Iterator[RemoteFile]: ...
    def find_child(self, parent_id: str, name: str, folder: bool | None = None) -> RemoteFile | None: ...
    def create_folder(self, parent_id: str, name: str) -> RemoteFile: ...
    def upload(self, local: str | Path, parent_id: str, name: str | None = None,
               mime_type: str | None = None) -> RemoteFile: ...
    def download(self, file_id: str, local: str | Path) -> Path: ...


class IntegrityError(RuntimeError):
    pass


def md5_file(path: str | Path, chunk: int = 4 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify(local: str | Path, remote: RemoteFile) -> None:
    if remote.md5 is None:
        return  # Google-native docs have no md5; nothing to compare
    got = md5_file(local)
    if got != remote.md5:
        raise IntegrityError(f"MD5 mismatch for {remote.name}: local {got} != remote {remote.md5}")


def ensure_folder(store: Store, parent_id: str, name: str, report: list | None = None) -> RemoteFile:
    existing = store.find_child(parent_id, name, folder=True)
    if existing:
        if report is not None:
            report.append(("exists", name, existing.id))
        return existing
    created = store.create_folder(parent_id, name)
    if report is not None:
        report.append(("created", name, created.id))
    return created


def ensure_structure(store: Store, parent_id: str, root_name: str = STUDIO_ROOT_NAME,
                     structure: dict[str, list[str]] | None = None) -> tuple[dict[str, str], list]:
    """Find-or-create the studio folder tree. Returns ({'01_Brand_Library/Logos': id, ...}, report)."""
    report: list = []
    root = ensure_folder(store, parent_id, root_name, report)
    ids = {"": root.id}
    for top, subs in (structure or STUDIO_STRUCTURE).items():
        top_f = ensure_folder(store, root.id, top, report)
        ids[top] = top_f.id
        for sub in subs:
            ids[f"{top}/{sub}"] = ensure_folder(store, top_f.id, sub, report).id
    return ids, report


def walk(store: Store, folder_id: str, path: str = "", max_depth: int = 20,
         max_items: int | None = None) -> Iterator[tuple[str, RemoteFile]]:
    """Breadth-first walk yielding (relative_path, file). Pages lazily, so huge trees stream."""
    queue = [(folder_id, path, 0)]
    seen = 0
    while queue:
        fid, prefix, depth = queue.pop(0)
        for f in store.list_children(fid):
            rel = f"{prefix}/{f.name}" if prefix else f.name
            yield rel, f
            seen += 1
            if max_items and seen >= max_items:
                return
            if f.is_folder and depth + 1 < max_depth:
                queue.append((f.id, rel, depth + 1))

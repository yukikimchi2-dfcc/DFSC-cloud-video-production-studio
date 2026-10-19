"""Asset index: a JSONL catalogue of what exists on Drive, instead of copying the files.

Each line records one file: source store, file id, path, version, md5, size, mime type,
modified time, plus team-maintained metadata (purpose, brand, review status). Scanning is
incremental and batched: `scan()` stops after `batch_size` new/changed entries, so a large
Drive is indexed over several runs without downloading anything.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .base import Store, walk

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mxf", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".psd", ".ai", ".svg", ".eps", ".pdf"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff"}
FONT_EXT = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}

EDITABLE_FIELDS = ("purpose", "brand", "review_status", "notes", "project")


def kind_of(name: str, mime: str) -> str:
    ext = Path(name).suffix.lower()
    if mime == "application/vnd.google-apps.folder":
        return "folder"
    for kind, exts in (("video", VIDEO_EXT), ("image", IMAGE_EXT), ("audio", AUDIO_EXT), ("font", FONT_EXT)):
        if ext in exts:
            return kind
    if mime.startswith("application/vnd.google-apps"):
        return "google_doc"
    return "other"


class AssetIndex:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    e = json.loads(line)
                    self.entries[e["key"]] = e

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for e in sorted(self.entries.values(), key=lambda e: e["path"]):
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    def scan(self, store: Store, folder_id: str, root_label: str = "", batch_size: int = 500,
             brand: str | None = None) -> dict:
        """Index up to `batch_size` new or changed files under folder_id. Returns counts."""
        counts = {"seen": 0, "new": 0, "changed": 0, "unchanged": 0}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for rel, f in walk(store, folder_id, root_label):
            counts["seen"] += 1
            key = f"{store.name}:{f.id}"
            old = self.entries.get(key)
            entry = {
                "key": key, "store": store.name, "id": f.id, "path": rel, "name": f.name,
                "kind": kind_of(f.name, f.mime_type), "mime_type": f.mime_type, "size": f.size, "md5": f.md5,
                "modified": f.modified, "version": f.version, "web_link": f.web_link, "indexed_at": now,
            }
            for field in EDITABLE_FIELDS:  # team-maintained metadata survives rescans
                entry[field] = (old or {}).get(field)
            if brand and not entry["brand"]:
                entry["brand"] = brand
            if entry["review_status"] is None:
                entry["review_status"] = "UNREVIEWED"
            if old is None:
                counts["new"] += 1
            elif (old.get("md5"), old.get("modified"), old.get("path")) != (f.md5, f.modified, rel):
                entry["previous_versions"] = (old.get("previous_versions") or []) + [
                    {"md5": old.get("md5"), "modified": old.get("modified"), "version": old.get("version")}]
                counts["changed"] += 1
            else:
                counts["unchanged"] += 1
                entry["previous_versions"] = old.get("previous_versions")
            self.entries[key] = entry
            if counts["new"] + counts["changed"] >= batch_size:
                counts["batch_limit_reached"] = True
                break
        self.save()
        return counts

    def annotate(self, key: str, **fields) -> dict:
        bad = set(fields) - set(EDITABLE_FIELDS)
        if bad:
            raise ValueError(f"not editable: {sorted(bad)}; editable: {EDITABLE_FIELDS}")
        self.entries[key].update(fields)
        self.save()
        return self.entries[key]

    def query(self, kind: str | None = None, brand: str | None = None, review_status: str | None = None,
              text: str | None = None) -> list[dict]:
        out = []
        for e in self.entries.values():
            if kind and e["kind"] != kind:
                continue
            if brand and e.get("brand") != brand:
                continue
            if review_status and e.get("review_status") != review_status:
                continue
            if text and text.lower() not in e["path"].lower():
                continue
            out.append(e)
        return sorted(out, key=lambda e: e["path"])

    def summary(self) -> dict:
        by_kind: dict[str, int] = {}
        for e in self.entries.values():
            by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        return {"total": len(self.entries), "by_kind": by_kind}

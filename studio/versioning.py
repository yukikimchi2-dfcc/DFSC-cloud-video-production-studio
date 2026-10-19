"""Never-overwrite output naming: <project>_v001_preview.mp4, <project>_v002_final.mp4, ...

The version counter is shared across modes within one output directory, so the
sequence reflects the real order of renders. Reservation uses O_EXCL file
creation, so two renders started at the same time can never get the same name.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_PATTERN = re.compile(r"^(?P<name>.+)_v(?P<ver>\d{3,})_(?P<mode>[a-z0-9]+)\.(?P<ext>\w+)$")


def existing_versions(out_dir: Path, name: str) -> list[int]:
    if not out_dir.exists():
        return []
    versions = []
    for p in out_dir.iterdir():
        m = _PATTERN.match(p.name)
        if m and m["name"] == name:
            versions.append(int(m["ver"]))
    return sorted(versions)


def reserve_output(out_dir: str | Path, name: str, mode: str, ext: str = "mp4") -> Path:
    """Atomically create an empty placeholder at the next free version and return its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nxt = (existing_versions(out_dir, name) or [0])[-1] + 1
    while True:
        path = out_dir / f"{name}_v{nxt:03d}_{mode}.{ext}"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return path
        except FileExistsError:
            nxt += 1


def parse(path: str | Path) -> dict | None:
    m = _PATTERN.match(Path(path).name)
    return None if not m else {"name": m["name"], "version": int(m["ver"]), "mode": m["mode"], "ext": m["ext"]}

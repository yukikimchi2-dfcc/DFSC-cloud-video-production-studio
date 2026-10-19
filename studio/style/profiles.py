"""Style Profiles: reusable, reviewable style memory stored as YAML in style_profiles/.

A profile is only a brand standard once a reviewer marks it APPROVED. Profiles created from
analysis always start UNREVIEWED; every status change is appended to `history`.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import STYLE_PROFILES_DIR, load_yaml, save_yaml

STATUSES = ("APPROVED", "REFERENCE_ONLY", "REJECTED", "UNREVIEWED")


@dataclass
class StyleProfile:
    name: str
    description: str = ""
    review_status: str = "UNREVIEWED"
    category_only: bool = False                    # True = starter category, no analysed data yet
    source_videos: list[dict] = field(default_factory=list)       # {path|drive_id, title, approved_version}
    reference_timecodes: list[dict] = field(default_factory=list)  # {source, t, note}
    key_frames: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    editing: dict = field(default_factory=dict)    # average_shot_length, cuts_per_minute, hook ...
    animation: dict = field(default_factory=dict)  # easing, durations, template ids ...
    visual: dict = field(default_factory=dict)     # palette, contrast, saturation, text zone ...
    audio: dict = field(default_factory=dict)      # bpm, loudness, sfx density ...
    use_cases: list[str] = field(default_factory=list)
    related_code: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", name).strip("_") or "profile"


def _path(name: str, root: Path) -> Path:
    return root / f"{_slug(name)}.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_profile(p: StyleProfile, root: Path = STYLE_PROFILES_DIR) -> Path:
    if p.review_status not in STATUSES:
        raise ValueError(f"review_status must be one of {STATUSES}")
    path = _path(p.name, root)
    save_yaml(path, p.to_dict())
    return path


def load_profile(name: str, root: Path = STYLE_PROFILES_DIR) -> StyleProfile:
    data = load_yaml(_path(name, root))
    known = StyleProfile.__dataclass_fields__
    return StyleProfile(**{k: v for k, v in data.items() if k in known})


def load_profiles(root: Path = STYLE_PROFILES_DIR, status: str | None = None) -> list[StyleProfile]:
    out = []
    for f in sorted(Path(root).glob("*.yaml")):
        data = load_yaml(f)
        if "name" not in data:
            continue
        p = StyleProfile(**{k: v for k, v in data.items() if k in StyleProfile.__dataclass_fields__})
        if status is None or p.review_status == status:
            out.append(p)
    return out


def create_profile_from_analysis(analysis: dict, name: str, description: str = "", use_cases: list[str] | None = None,
                                 root: Path = STYLE_PROFILES_DIR, overwrite: bool = False) -> StyleProfile:
    """Turn an analyzer result into an UNREVIEWED profile (never auto-approved)."""
    if _path(name, root).exists() and not overwrite:
        raise FileExistsError(f"Profile '{name}' already exists; pass overwrite=True or choose another name")
    e, col = analysis.get("editing", {}), analysis.get("colour", {})
    p = StyleProfile(
        name=name, description=description, review_status="UNREVIEWED",
        source_videos=[{"path": analysis.get("source"), "duration": analysis.get("format", {}).get("duration")}],
        reference_timecodes=[{"source": analysis.get("source"), "t": c, "note": "cut"} for c in e.get("cut_times", [])[:20]],
        key_frames=[k["file"] for k in analysis.get("keyframes", [])],
        editing={k: e.get(k) for k in ("average_shot_length", "median_shot_length", "cuts_per_minute", "pacing_cuts_per_5s")}
        | {"hook": analysis.get("hook"), "camera_motion": analysis.get("camera_motion")},
        visual={"palette": col.get("palette"), "brightness": col.get("brightness"), "contrast": col.get("contrast"),
                "saturation": col.get("saturation"), "text": analysis.get("text")},
        audio=analysis.get("audio", {}),
        use_cases=use_cases or [],
        related_code=["studio/style/analyzer.py"],
        history=[{"at": _now(), "action": "created_from_analysis", "by": "style-analyzer", "status": "UNREVIEWED"}],
    )
    save_profile(p, root)
    return p


def set_review_status(name: str, status: str, reviewer: str, note: str = "", root: Path = STYLE_PROFILES_DIR) -> StyleProfile:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if not reviewer:
        raise ValueError("a reviewer name is required to change review status")
    p = load_profile(name, root)
    if status == "APPROVED" and p.category_only:
        raise ValueError(f"'{name}' is a starter category with no analysed source — analyse real videos first")
    p.history.append({"at": _now(), "action": "review", "by": reviewer, "from": p.review_status, "status": status, "note": note})
    p.review_status = status
    save_profile(p, root)
    return p


def get_brand_standard(name: str | None = None, root: Path = STYLE_PROFILES_DIR) -> list[StyleProfile] | StyleProfile:
    """Only APPROVED profiles can act as a brand standard."""
    approved = load_profiles(root, status="APPROVED")
    if name is None:
        return approved
    for p in approved:
        if p.name == name:
            return p
    raise LookupError(f"No APPROVED style profile named '{name}' (unreviewed or rejected profiles cannot be used as a standard)")

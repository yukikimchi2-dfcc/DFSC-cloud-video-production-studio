"""Per-project brand kit: colours, fonts, logos, motion defaults.

Each project owns projects/<id>/brand/brand.yaml — nothing here is hard-coded to one brand.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageFont

from .config import PROJECTS_DIR, REPO_ROOT, load_yaml
from .core import vector

# Fallback fonts present in the studio image (Dockerfile installs fonts-noto-cjk + fonts-noto-cjk-extra).
# Face index inside the NotoSansCJK-*.ttc collections: 0 JP, 1 KR, 2 SC, 3 TC, 4 HK.
_NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-{}.ttc"
_TC, _HK, _SC = 3, 4, 2
SYSTEM_FONTS = {
    **{f"cjk_{w.lower()}": {"path": _NOTO.format(w), "index": _TC}
       for w in ("Thin", "Light", "DemiLight", "Regular", "Medium", "Bold", "Black")},
    **{f"cjk_{w.lower()}_hk": {"path": _NOTO.format(w), "index": _HK}
       for w in ("Thin", "Light", "DemiLight", "Regular", "Medium", "Bold", "Black")},
    **{f"cjk_{w.lower()}_sc": {"path": _NOTO.format(w), "index": _SC} for w in ("Regular", "Bold", "Black")},
    "emoji": {"path": "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", "index": 0},
}


class FontMissingError(RuntimeError):
    pass


@dataclass
class BrandKit:
    project_id: str
    name: str
    colors: dict[str, str]
    fonts: dict[str, dict]
    logos: dict[str, str] = field(default_factory=dict)
    motion: dict = field(default_factory=dict)
    root: Path = REPO_ROOT

    @classmethod
    def load(cls, project_id: str) -> "BrandKit":
        root = PROJECTS_DIR / project_id / "brand"
        data = load_yaml(root / "brand.yaml")
        return cls(project_id=project_id, name=data.get("name", project_id), colors=data.get("colors", {}),
                   fonts=data.get("fonts", {}), logos=data.get("logos", {}), motion=data.get("motion", {}),
                   root=root)

    @classmethod
    def neutral(cls) -> "BrandKit":
        """Unbranded kit for tests and projects without a brand file yet."""
        return cls("neutral", "Neutral",
                   colors={"primary": "#FFFFFF", "secondary": "#888888", "accent": "#FFD400",
                           "background": "#000000", "text": "#FFFFFF"},
                   fonts={"title": {"system": "cjk_black"}, "body": {"system": "cjk_regular"},
                          "subtitle": {"system": "cjk_bold"}})

    def color(self, key: str) -> str:
        """Resolve a palette key ('primary') or pass through a literal colour ('#FF0000')."""
        if key.startswith("#") or key.startswith("rgb"):
            return key
        if key not in self.colors:
            raise KeyError(f"Brand '{self.name}' has no colour '{key}'. Defined: {sorted(self.colors)}")
        return self.colors[key]

    def font_spec(self, role: str) -> dict:
        spec = self.fonts.get(role) or self.fonts.get("body") or {"system": "cjk_regular"}
        if "system" in spec:
            return SYSTEM_FONTS[spec["system"]]
        path = Path(spec["path"])
        if not path.is_absolute():
            path = self.root / path
        return {"path": str(path), "index": spec.get("index", 0)}

    def font(self, role: str, size: int) -> ImageFont.FreeTypeFont:
        spec = self.font_spec(role)
        return _load_font(spec["path"], spec.get("index", 0), int(size))

    def logo(self, key: str) -> Path:
        path = Path(self.logos[key])
        return path if path.is_absolute() else self.root / path

    def logo_shape(self, key: str) -> dict:
        return vector.load_shape(self.logo(key))

    def check_fonts(self) -> list[str]:
        """Return a list of problems (missing files) — used by QC before rendering."""
        problems = []
        for role in self.fonts:
            spec = self.font_spec(role)
            if not Path(spec["path"]).exists():
                problems.append(f"font role '{role}': file not found {spec['path']}")
        return problems


@functools.lru_cache(maxsize=256)
def _load_font(path: str, index: int, size: int) -> ImageFont.FreeTypeFont:
    if not Path(path).exists():
        raise FontMissingError(f"Font file not found: {path}")
    return ImageFont.truetype(path, size=size, index=index)


def load_brand(project_id: str | None) -> BrandKit:
    if not project_id:
        return BrandKit.neutral()
    if not (PROJECTS_DIR / project_id / "brand" / "brand.yaml").exists():
        return BrandKit.neutral()
    return BrandKit.load(project_id)

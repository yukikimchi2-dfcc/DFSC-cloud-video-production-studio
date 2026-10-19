"""Layered configuration: studio defaults -> project overrides -> call-site overrides."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
PROJECTS_DIR = REPO_ROOT / "projects"
STYLE_PROFILES_DIR = REPO_ROOT / "style_profiles"
TEMPLATES_DIR = REPO_ROOT / "templates"


def deep_merge(base: dict, override: dict | None) -> dict:
    """Return a new dict with `override` merged into `base` recursively (override wins)."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_yaml(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: str | Path, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_defaults() -> dict:
    return load_yaml(CONFIG_DIR / "defaults.yaml")


def load_config(project_id: str | None = None, overrides: dict | None = None) -> dict:
    cfg = load_defaults()
    if project_id:
        project_file = PROJECTS_DIR / project_id / "project.yaml"
        if not project_file.exists():
            raise FileNotFoundError(f"Unknown project '{project_id}': {project_file} not found")
        cfg = deep_merge(cfg, load_yaml(project_file).get("overrides", {}))
    return deep_merge(cfg, overrides)


def get(cfg: dict, dotted: str, default: Any = None) -> Any:
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node

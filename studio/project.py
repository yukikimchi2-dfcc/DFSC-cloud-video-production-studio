"""Projects: scaffolding, status workflow with role permissions, activity log, handover notes.

A project lives in projects/<id>/ and is fully described by files in git:
  project.yaml      metadata, status, overrides, Drive folder id
  brand/brand.yaml  the project's own brand kit (or copy of a shared one)
  activity.jsonl    append-only log of status changes, renders, notes
  HANDOVER.md       regenerated summary so anyone can pick the project up cold
"""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from .config import CONFIG_DIR, PROJECTS_DIR, load_yaml, save_yaml
from .render.renderer import git_commit, render_history

TEMPLATE_DIR = PROJECTS_DIR / "_template"


class PermissionDenied(PermissionError):
    pass


def roles_config() -> dict:
    return load_yaml(CONFIG_DIR / "roles.yaml")


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def list_projects() -> list[dict]:
    out = []
    for p in sorted(PROJECTS_DIR.iterdir()):
        if p.is_dir() and not p.name.startswith("_") and (p / "project.yaml").exists():
            out.append(load_yaml(p / "project.yaml"))
    return out


def create_project(project_id: str, name: str, project_type: str = "promo", brand_from: str | None = None,
                   owner: str | None = None) -> Path:
    dest = project_dir(project_id)
    if dest.exists():
        raise FileExistsError(f"project '{project_id}' already exists — refusing to overwrite")
    shutil.copytree(TEMPLATE_DIR, dest)
    meta = load_yaml(dest / "project.yaml")
    meta.update({"id": project_id, "name": name, "type": project_type, "owner": owner,
                 "created": date.today().isoformat(), "status": "Not Started"})
    save_yaml(dest / "project.yaml", meta)
    if brand_from:
        src = project_dir(brand_from) / "brand"
        shutil.rmtree(dest / "brand")
        shutil.copytree(src, dest / "brand", ignore=shutil.ignore_patterns("source"))
    log(project_id, "created", user=owner, detail={"name": name, "type": project_type, "brand_from": brand_from})
    write_handover(project_id)
    return dest


def log(project_id: str, event: str, user: str | None = None, detail: dict | None = None) -> dict:
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, "user": user,
           "commit": git_commit(), "detail": detail or {}}
    with open(project_dir(project_id) / "activity.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def activity(project_id: str, last: int | None = None) -> list[dict]:
    path = project_dir(project_id) / "activity.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-last:] if last else rows


def set_status(project_id: str, new_status: str, user: str, role: str, note: str = "") -> dict:
    cfg = roles_config()
    if role not in cfg["roles"]:
        raise PermissionDenied(f"unknown role '{role}'. Roles: {list(cfg['roles'])}")
    meta_path = project_dir(project_id) / "project.yaml"
    meta = load_yaml(meta_path)
    old = meta.get("status", "Not Started")
    allowed = cfg["transitions"].get(old, {})
    if new_status not in allowed:
        raise PermissionDenied(f"'{old}' -> '{new_status}' is not a valid step. From '{old}' you can go to: {list(allowed)}")
    needed = allowed[new_status]
    perms = cfg["roles"][role]["can"]
    if "*" not in perms and needed != "*" and needed not in perms:
        raise PermissionDenied(f"role '{role}' cannot '{needed}' (needed for {old} -> {new_status})")
    if needed == "*" and "*" not in perms:
        raise PermissionDenied(f"only Admin can move a project to '{new_status}'")
    meta["status"] = new_status
    save_yaml(meta_path, meta)
    rec = log(project_id, "status", user=user, detail={"from": old, "to": new_status, "role": role, "note": note})
    write_handover(project_id)
    return rec


def update_handover_fields(project_id: str, **fields) -> None:
    """Editable handover facts kept in project.yaml under `handover:` (todo, known_issues, next_action, assets, templates)."""
    meta_path = project_dir(project_id) / "project.yaml"
    meta = load_yaml(meta_path)
    meta.setdefault("handover", {}).update(fields)
    save_yaml(meta_path, meta)
    write_handover(project_id)


def write_handover(project_id: str, renders_dir: Path | None = None) -> Path:
    from .config import REPO_ROOT, load_config
    meta = load_yaml(project_dir(project_id) / "project.yaml")
    h = meta.get("handover", {})
    cfg = load_config(project_id)
    renders = render_history(renders_dir or REPO_ROOT / cfg["studio"]["renders_dir"] / project_id)
    last_render = renders[-1] if renders else None
    recent = activity(project_id, last=8)
    out = load_yaml(CONFIG_DIR / "drive_output.yaml") if (CONFIG_DIR / "drive_output.yaml").exists() else {}
    out_folders = out.get("folders", {})

    def bullets(items, empty="（无）"):
        return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"

    lines = [
        f"# 项目交接 · {meta.get('name', project_id)}",
        "",
        "> 本文件由 `studio project handover` 自动生成，请勿手动编辑；修改请用命令或改 project.yaml 的 handover 区块。",
        "",
        "| 项目 | 内容 |", "|---|---|",
        f"| 项目 ID | `{project_id}` |",
        f"| 当前状态 | **{meta.get('status')}** |",
        f"| 负责人 | {meta.get('owner') or '未指定'} |",
        f"| 风格档案 | {meta.get('style_profile') or '未指定（尚无 APPROVED 风格）'} |",
        f"| 生成时代码版本 | `{git_commit() or 'unknown'}`（最新以分支 HEAD 为准） |",
        f"| Drive 输出根目录 | {out.get('root', {}).get('id') or '未建立'}（`config/drive_output.yaml`） |",
        f"| Drive 项目文件夹 | {meta.get('drive', {}).get('folder_id') or '未连接'} |",
        f"| Drive 预览目录 | {out_folders.get(f'06_Project_Previews/{project_id}') or '未建立'} |",
        f"| Drive QC 目录 | {out_folders.get(f'08_QC_Reports/{project_id}') or '未建立'} |",
        "",
        "## 最近一次渲染",
        (f"- `{Path(last_render['path']).name}` · {last_render['mode']} · {last_render['width']}x{last_render['height']}"
         f" · {last_render['duration']:.1f}s · {last_render['size_mb']} MB · commit `{last_render.get('git_commit')}`"
         f" · {last_render['created_at']}" if last_render else "- 尚未渲染"),
        "",
        "## 使用素材", bullets(h.get("assets", [])),
        "", "## 使用模板", bullets(h.get("templates", [])),
        "", "## 待完成事项", bullets(h.get("todo", [])),
        "", "## 已知问题", bullets(h.get("known_issues", [])),
        "", "## 下一步行动", bullets([h["next_action"]] if h.get("next_action") else []),
        "", "## 最近修改",
        bullets([f"{r['at']} · {r['event']} · {r.get('user') or '-'} · "
                 + (f"{r['detail'].get('from')} → {r['detail'].get('to')}" if r["event"] == "status" else
                    json.dumps(r["detail"], ensure_ascii=False)) for r in reversed(recent)]),
        "",
    ]
    path = project_dir(project_id) / "HANDOVER.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

#!/usr/bin/env python3
"""Pull a project's reference material and turn it into reviewable style intelligence.

For projects/<id>/project.yaml:
  drive.reference_folders   public ("anyone with the link") Drive folders -> listed with gdown,
                            indexed, and their videos downloaded into workspace/references/
  references.facebook       public Facebook videos/reels -> downloaded with yt-dlp
Then every downloaded video is run through the style analyzer, producing a report and an
UNREVIEWED style profile, plus a summary at projects/<id>/references/REFERENCE_SUMMARY.md.

Nothing is moved or deleted anywhere; Drive is only read. Private folders need the
service-account path instead (docs/zh/03_Google_Drive_连接.md).

Usage:
  python tools/ingest_references.py dfsc-2027 [--max-videos 20] [--list-only] [--no-analyze]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from studio.config import PROJECTS_DIR, REPO_ROOT, load_yaml  # noqa: E402
from studio.storage.index import VIDEO_EXT, AssetIndex, kind_of  # noqa: E402

WORK = REPO_ROOT / "workspace" / "references"


def folder_id(url: str) -> str:
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(f"not a Drive folder link: {url}")
    return m.group(1)


def list_drive_folder(url: str) -> list[dict]:
    import gdown
    fid = folder_id(url)
    out = WORK / "drive" / fid
    items = gdown.download_folder(url=url, output=str(out), skip_download=True, quiet=True) or []
    return [{"id": it.id, "path": it.path, "local_path": it.local_path, "folder": fid} for it in items]


def index_listing(idx: AssetIndex, listing: list[dict], brand: str) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for it in listing:
        key = f"gdrive:{it['id']}"
        old = idx.entries.get(key, {})
        name = Path(it["path"]).name
        idx.entries[key] = {
            **old, "key": key, "store": "gdrive", "id": it["id"], "path": f"{it['folder']}/{it['path']}",
            "name": name, "kind": kind_of(name, ""), "mime_type": None, "size": old.get("size"), "md5": None,
            "modified": None, "version": None, "web_link": f"https://drive.google.com/file/d/{it['id']}/view",
            "indexed_at": now, "brand": old.get("brand") or brand, "purpose": old.get("purpose") or "reference",
            "review_status": old.get("review_status") or "UNREVIEWED", "notes": old.get("notes"),
            "project": old.get("project"),
        }
    idx.save()


def download_drive_file(it: dict) -> Path | None:
    import gdown
    dest = Path(it["local_path"])
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    got = gdown.download(id=it["id"], output=str(dest), quiet=True, resume=True)
    return Path(got) if got else None


def download_facebook(url: str) -> Path | None:
    import yt_dlp
    out = WORK / "facebook"
    out.mkdir(parents=True, exist_ok=True)
    opts = {"outtmpl": str(out / "%(id)s.%(ext)s"), "quiet": True, "noprogress": True,
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", "merge_output_format": "mp4"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
        meta = {k: info.get(k) for k in ("id", "title", "uploader", "upload_date", "duration", "description", "webpage_url")}
        path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return path if path.exists() else None


def analyze(video: Path, project_id: str, label: str) -> dict:
    from studio.style.analyzer import analyze_video, write_style_report
    from studio.style.profiles import STYLE_PROFILES_DIR, _path, create_profile_from_analysis
    analysis = analyze_video(video)
    report_dir = PROJECTS_DIR / project_id / "references" / "style_reports"
    md, js = write_style_report(analysis, report_dir, stem=video.stem)
    profile = f"Ref_{project_id}_{re.sub(r'[^A-Za-z0-9]+', '_', video.stem)[:40]}"
    if not _path(profile, STYLE_PROFILES_DIR).exists():  # re-runs never touch a profile someone already reviewed
        create_profile_from_analysis(analysis, profile, description=f"Auto-analysed reference: {label}")
    e = analysis["editing"]
    return {"video": label, "report": str(md.relative_to(REPO_ROOT)), "profile": profile,
            "duration": analysis["format"]["duration"], "shots": e["shots"],
            "avg_shot": e["average_shot_length"], "cuts_per_min": e["cuts_per_minute"],
            "bpm": (analysis.get("audio") or {}).get("bpm")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--max-videos", type=int, default=20, help="per run; large folders are processed in batches")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--no-analyze", action="store_true")
    args = ap.parse_args()

    meta = load_yaml(PROJECTS_DIR / args.project / "project.yaml")
    brand = args.project
    idx = AssetIndex(REPO_ROOT / "workspace" / "asset_index.jsonl")
    log: dict = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "drive": [], "facebook": [],
                 "analyzed": [], "errors": []}
    videos: list[tuple[Path, str]] = []

    for url in (meta.get("drive") or {}).get("reference_folders", []):
        try:
            listing = list_drive_folder(url)
            index_listing(idx, listing, brand)
            vids = [it for it in listing if Path(it["path"]).suffix.lower() in VIDEO_EXT]
            log["drive"].append({"url": url, "files": len(listing), "videos": len(vids),
                                 "sample": [it["path"] for it in listing[:30]]})
            print(f"drive {folder_id(url)}: {len(listing)} files, {len(vids)} videos")
            if not args.list_only:
                for it in vids[: max(args.max_videos - len(videos), 0)]:
                    p = download_drive_file(it)
                    if p:
                        videos.append((p, f"Drive: {it['path']}"))
        except Exception as e:  # noqa: BLE001 — keep going with other sources
            log["errors"].append(f"{url}: {type(e).__name__}: {e}")
            traceback.print_exc()

    for url in (meta.get("references") or {}).get("facebook", []):
        if args.list_only:
            break
        try:
            p = download_facebook(url)
            log["facebook"].append({"url": url, "file": p and p.name})
            if p:
                videos.append((p, f"Facebook: {url}"))
        except Exception as e:  # noqa: BLE001
            log["errors"].append(f"{url}: {type(e).__name__}: {e}")
            traceback.print_exc()

    if not args.no_analyze:
        for path, label in videos:
            try:
                log["analyzed"].append(analyze(path, args.project, label))
                print(f"analyzed {label}")
            except Exception as e:  # noqa: BLE001
                log["errors"].append(f"analyze {label}: {type(e).__name__}: {e}")

    out = PROJECTS_DIR / args.project / "references"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ingest_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 参考资料汇总 · {args.project}", "", f"- 执行时间：{log['run_at']}",
             "- 所有风格档案为 **UNREVIEWED**：存在于 Drive / Facebook 不代表是认可的作品，需 Reviewer 审核。", "",
             "## Google Drive 文件夹", ""]
    for d in log["drive"]:
        lines += [f"- {d['url']} — {d['files']} 个文件，{d['videos']} 支影片"]
    lines += ["", "## 已分析影片", "", "| 影片 | 时长 | 镜头数 | 平均镜头 | 每分钟剪辑 | BPM | 报告 | 风格档案 |", "|---|---|---|---|---|---|---|---|"]
    for a in log["analyzed"]:
        lines.append(f"| {a['video']} | {a['duration']:.1f}s | {a['shots']} | {a['avg_shot']:.2f}s | {a['cuts_per_min']:.1f} | "
                     f"{a['bpm'] or '-'} | {a['report']} | {a['profile']} |")
    if log["errors"]:
        lines += ["", "## 错误", ""] + [f"- {e}" for e in log["errors"]]
    (out / "REFERENCE_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"summary -> {out / 'REFERENCE_SUMMARY.md'}  ({len(log['errors'])} errors)")
    return 1 if log["errors"] and not log["analyzed"] and not log["drive"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

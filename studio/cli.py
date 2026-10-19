"""`studio` command line — the single entry point for the team.

    studio audit                          environment check (what exists / what is blocked)
    studio project list|new|status|handover|log
    studio render test-card --mode preview
    studio queue add|list|run|show
    studio templates list|preview
    studio qc VIDEO
    studio style analyze VIDEO | list | review NAME STATUS
    studio drive check|setup|scan|upload|download
    studio brand extract SOURCE.ai OUT --groups groups.yaml
    studio references ingest PROJECT      reference Drive folders + Facebook videos -> style reports
    studio models fetch                   local Whisper large-v3-turbo (free CPU transcription)
    studio gpu estimate --seconds 60
Run `studio <command> -h` for options.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import REPO_ROOT, load_config


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _user() -> str:
    return os.environ.get("STUDIO_USER") or os.environ.get("USER") or "unknown"


# ---------------------------------------------------------------- audit
def cmd_audit(a):
    from .audit import run_audit
    _print(run_audit(check_network=not a.offline))


# ---------------------------------------------------------------- project
def cmd_project(a):
    from . import project as P
    if a.action == "list":
        for p in P.list_projects():
            print(f"{p['id']:<24} {p.get('status', '?'):<18} {p.get('name', '')}")
    elif a.action == "new":
        path = P.create_project(a.id, a.name or a.id, a.type, a.brand_from, owner=_user())
        print(f"created {path}")
    elif a.action == "status":
        if a.set:
            _print(P.set_status(a.id, a.set, _user(), a.role, a.note or ""))
        else:
            print((P.project_dir(a.id) / "HANDOVER.md").read_text(encoding="utf-8"))
    elif a.action == "handover":
        fields = {k: v for k, v in {"next_action": a.next_action, "todo": a.todo, "known_issues": a.issue,
                                    "assets": a.asset, "templates": a.template}.items() if v}
        if fields:
            P.update_handover_fields(a.id, **fields)
        print(P.write_handover(a.id).read_text(encoding="utf-8"))
    elif a.action == "log":
        for r in P.activity(a.id, last=a.last):
            print(json.dumps(r, ensure_ascii=False))


# ---------------------------------------------------------------- render / queue
def cmd_render(a):
    from .render.demo import build_test_card
    from .render.renderer import Renderer
    tl = build_test_card(a.project, duration=a.duration, text=a.text, audio=a.audio)
    r = Renderer(a.project).render(tl, a.mode, name=a.name or "test_card", start=a.start, end=a.end,
                                   progress=_progress)
    print()
    _print(r.__dict__)


def _progress(done, total):
    if done == total or done % 10 == 0:
        sys.stdout.write(f"\r  rendering {done}/{total} frames")
        sys.stdout.flush()


def cmd_queue(a):
    from .render import queue as Q
    if a.action == "add":
        kwargs = json.loads(a.kwargs) if a.kwargs else {}
        invalidate = [tuple(map(float, r.split("-"))) for r in (a.invalidate or [])]
        job = Q.enqueue(a.builder, kwargs, a.mode, a.name, a.project, start=a.start, end=a.end,
                        chunk_seconds=a.chunk, invalidate=invalidate, upload=a.upload)
        print(f"queued {job['id']}")
    elif a.action == "list":
        for j in Q.list_jobs(state=a.state):
            print(f"{j['id']}  {j['state']:<8} {j['mode']:<8} {int(j['progress'] * 100):>3}%  "
                  f"attempts {j['attempts']}/{j['max_attempts']}  {j['builder']}")
    elif a.action == "show":
        _print(Q.load_job(a.job_id))
    elif a.action == "run":
        uploader = _drive_uploader() if a.upload else None
        for j in Q.run_pending(uploader=uploader):
            print(f"{j['id']} -> {j['state']} {j.get('result', {}) and j['result']['path'] or j.get('error')}")


def _drive_uploader():
    from .storage import get_store

    def upload(path, job):
        from .config import load_yaml, PROJECTS_DIR
        meta = load_yaml(PROJECTS_DIR / job["project_id"] / "project.yaml") if job.get("project_id") else {}
        folder = (meta.get("drive") or {}).get("previews_folder_id") or os.environ.get("STUDIO_DRIVE_PREVIEWS_FOLDER")
        if not folder:
            raise RuntimeError("no Drive previews folder configured (project.yaml drive.previews_folder_id)")
        return get_store().upload(path, folder).__dict__
    return upload


# ---------------------------------------------------------------- templates
def cmd_templates(a):
    from .motion import templates as T
    if a.action == "list":
        for t in T.list_templates():
            print(f"{t['id']:<32} v{t.get('version', '?'):<6} {t.get('category', ''):<14} {t.get('name', '')}")
    elif a.action == "preview":
        out = Path(a.out or REPO_ROOT / "templates" / a.id)
        _print(T.render_template_preview(a.id, out, project_id=a.project))


# ---------------------------------------------------------------- qc / style
def cmd_qc(a):
    from .brand import load_brand
    from .qc.checks import run_qc
    from .qc.report import write_report
    cfg = load_config(a.project)
    from .versioning import parse
    mode = a.mode or (parse(a.video) or {}).get("mode")
    loudness = cfg["render"]["final"]["loudness_lufs"] if mode == "final" else None  # true peak read from config
    report = run_qc(a.video, cfg, brand=load_brand(a.project) if a.project else None, loudness_target=loudness)
    out = Path(a.out or REPO_ROOT / "workspace" / "qc")
    md, js = write_report(report, out)
    print(f"QC {'PASSED' if report.passed else 'FAILED'} -> {md}")
    sys.exit(0 if report.passed else 1)


def cmd_style(a):
    from .style import profiles as SP
    if a.action == "analyze":
        from .style.analyzer import analyze_video, write_style_report
        analysis = analyze_video(a.video)
        out = Path(a.out or REPO_ROOT / "workspace" / "style" / Path(a.video).stem)
        print(write_style_report(analysis, out))
        if a.profile:
            SP.create_profile_from_analysis(analysis, a.profile)
            print(f"created UNREVIEWED profile {a.profile}")
    elif a.action == "list":
        for p in SP.load_profiles():
            name = p.name if hasattr(p, "name") else p["name"]
            status = p.review_status if hasattr(p, "review_status") else p["review_status"]
            print(f"{name:<32} {status}")
    elif a.action == "review":
        SP.set_review_status(a.name, a.status, _user(), a.note or "")
        print(f"{a.name} -> {a.status}")


# ---------------------------------------------------------------- drive
def cmd_drive(a):
    from .storage import ensure_structure, get_store
    from .storage.index import AssetIndex
    store = get_store(a.store)
    if a.action == "check":
        _print(_drive_check(store, a.folder))
    elif a.action == "setup":
        ids, report = ensure_structure(store, a.parent)
        for status, name, fid in report:
            print(f"{status:<8} {name:<32} {fid}")
        _print(ids)
    elif a.action == "scan":
        idx = AssetIndex(a.index or REPO_ROOT / "workspace" / "asset_index.jsonl")
        _print(idx.scan(store, a.folder, a.label or "", batch_size=a.batch, brand=a.brand) | idx.summary())
    elif a.action == "upload":
        _print(store.upload(a.path, a.folder).__dict__)
    elif a.action == "download":
        print(store.download(a.file_id, a.dest))


def _drive_check(store, folder_id: str | None) -> dict:
    """Prove read + write + download + checksum on a real folder, then leave a marker file (no deletes)."""
    import tempfile
    from datetime import datetime, timezone
    result: dict = {"store": store.name}
    if hasattr(store, "about"):
        result["account"] = store.about().get("user")
    if not folder_id:
        result["note"] = "pass --folder FOLDER_ID to test read/write"
        return result
    result["read"] = [f.name for _, f in zip(range(10), store.list_children(folder_id))]
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / f"studio_access_check_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.txt"
        probe.write_text("Cloud Video Production Studio access check — safe to keep or archive.\n", encoding="utf-8")
        up = store.upload(probe, folder_id)
        back = store.download(up.id, Path(tmp) / "roundtrip.txt")
        result["write"] = {"id": up.id, "name": up.name, "md5": up.md5}
        result["download_verified"] = back.read_bytes() == probe.read_bytes()
    return result


# ---------------------------------------------------------------- brand / gpu
def cmd_brand(a):
    import subprocess
    sys.exit(subprocess.call([sys.executable, str(REPO_ROOT / "tools" / "extract_ai_assets.py"), a.source, a.out,
                              "--groups", a.groups]))


def cmd_references(a):
    import subprocess
    extra = (["--list-only"] if a.list_only else []) + (["--no-analyze"] if a.no_analyze else [])
    sys.exit(subprocess.call([sys.executable, str(REPO_ROOT / "tools" / "ingest_references.py"), a.project,
                              "--max-videos", str(a.max_videos), *extra]))


def cmd_models(a):
    import time
    from huggingface_hub import snapshot_download
    dest = REPO_ROOT / "workspace" / "models" / "faster-whisper-large-v3-turbo"
    t = time.time()
    path = snapshot_download(a.repo, local_dir=str(dest))
    print(f"Whisper model ready at {path} ({time.time() - t:.0f}s). Transcription uses it automatically.")


def cmd_gpu(a):
    from .gpu.guard import GpuPlan, estimate_render_hours
    hours = estimate_render_hours(a.seconds, a.renders, transcribe_minutes=a.transcribe_minutes)
    plan = GpuPlan(a.provider, a.gpu_type, a.hourly_usd, hours, load_config()["gpu"]["auto_stop_minutes"])
    _print({"plan": plan.__dict__, "est_cost_usd": plan.est_cost_usd,
            "note": "Estimate only. Starting a paid GPU needs config gpu.provider + STUDIO_GPU_APPROVAL."})


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="studio", description="Cloud AI Video Production Studio")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("audit", help="environment audit")
    s.add_argument("--offline", action="store_true", help="skip network reachability checks")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("project", help="projects, status, handover")
    s.add_argument("action", choices=["list", "new", "status", "handover", "log"])
    s.add_argument("id", nargs="?")
    s.add_argument("--name")
    s.add_argument("--type", default="promo")
    s.add_argument("--brand-from", help="copy brand kit from another project id")
    s.add_argument("--set", help="new status, e.g. 'Awaiting Review'")
    s.add_argument("--role", default="Editor")
    s.add_argument("--note")
    s.add_argument("--next-action")
    s.add_argument("--todo", action="append")
    s.add_argument("--issue", action="append")
    s.add_argument("--asset", action="append")
    s.add_argument("--template", action="append")
    s.add_argument("--last", type=int, default=20)
    s.set_defaults(fn=cmd_project)

    s = sub.add_parser("render", help="render the synthetic test card (system check)")
    s.add_argument("what", choices=["test-card"])
    s.add_argument("--mode", default="preview", choices=["preview", "final"])
    s.add_argument("--project", default="dfsc-2027")
    s.add_argument("--name")
    s.add_argument("--text", default="Cloud Video Studio")
    s.add_argument("--duration", type=float, default=4.0)
    s.add_argument("--audio")
    s.add_argument("--start", type=float, default=0.0)
    s.add_argument("--end", type=float)
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("queue", help="render queue")
    s.add_argument("action", choices=["add", "list", "show", "run"])
    s.add_argument("job_id", nargs="?")
    s.add_argument("--builder", default="studio.render.demo:build_test_card")
    s.add_argument("--kwargs", help="JSON kwargs for the builder")
    s.add_argument("--mode", default="preview")
    s.add_argument("--name")
    s.add_argument("--project")
    s.add_argument("--start", type=float, default=0.0, help="render only from this second")
    s.add_argument("--end", type=float, help="render only up to this second")
    s.add_argument("--chunk", type=float, help="chunk length in seconds (enables cache + partial re-render)")
    s.add_argument("--invalidate", action="append", help="re-render range, e.g. 2-4 (seconds)")
    s.add_argument("--upload", action="store_true", help="upload result to the project's Drive previews folder")
    s.add_argument("--state", choices=["queued", "running", "done", "failed"])
    s.set_defaults(fn=cmd_queue)

    s = sub.add_parser("templates", help="motion graphics templates")
    s.add_argument("action", choices=["list", "preview"])
    s.add_argument("id", nargs="?")
    s.add_argument("--project")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_templates)

    s = sub.add_parser("qc", help="quality-check a video")
    s.add_argument("video")
    s.add_argument("--mode", choices=["preview", "final"], help="final adds the LUFS / true-peak check (auto from filename)")
    s.add_argument("--project")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_qc)

    s = sub.add_parser("style", help="style intelligence")
    s.add_argument("action", choices=["analyze", "list", "review"])
    s.add_argument("video", nargs="?", help="video to analyze (analyze) or profile name (review)")
    s.add_argument("status", nargs="?", choices=["APPROVED", "REFERENCE_ONLY", "REJECTED", "UNREVIEWED"])
    s.add_argument("--out")
    s.add_argument("--profile", help="also create an UNREVIEWED style profile with this name")
    s.add_argument("--note")
    s.set_defaults(fn=lambda a: cmd_style(argparse.Namespace(**{**vars(a), "name": a.video})))

    s = sub.add_parser("drive", help="Google Drive asset system")
    s.add_argument("action", choices=["check", "setup", "scan", "upload", "download"])
    s.add_argument("--store", choices=["gdrive", "local"])
    s.add_argument("--folder", help="folder id")
    s.add_argument("--parent", help="parent folder id for setup")
    s.add_argument("--label")
    s.add_argument("--brand")
    s.add_argument("--batch", type=int, default=500)
    s.add_argument("--index")
    s.add_argument("--path")
    s.add_argument("--file-id")
    s.add_argument("--dest")
    s.set_defaults(fn=cmd_drive)

    s = sub.add_parser("brand", help="brand assets")
    s.add_argument("action", choices=["extract"])
    s.add_argument("source")
    s.add_argument("out")
    s.add_argument("--groups", required=True)
    s.set_defaults(fn=cmd_brand)

    s = sub.add_parser("references", help="ingest a project's reference Drive folders + Facebook videos, analyse style")
    s.add_argument("action", choices=["ingest"])
    s.add_argument("project")
    s.add_argument("--max-videos", type=int, default=20)
    s.add_argument("--list-only", action="store_true")
    s.add_argument("--no-analyze", action="store_true")
    s.set_defaults(fn=cmd_references)

    s = sub.add_parser("models", help="download the local Whisper model into workspace/models (needs huggingface.co)")
    s.add_argument("action", choices=["fetch"])
    s.add_argument("--repo", default="mobiuslabsgmbh/faster-whisper-large-v3-turbo")
    s.set_defaults(fn=cmd_models)

    s = sub.add_parser("gpu", help="GPU cost estimate (never starts anything)")
    s.add_argument("action", choices=["estimate"])
    s.add_argument("--seconds", type=float, required=True, help="finished video length")
    s.add_argument("--renders", type=int, default=3)
    s.add_argument("--transcribe-minutes", type=float, default=0.0)
    s.add_argument("--provider", default="runpod")
    s.add_argument("--gpu-type", default="RTX 4090")
    s.add_argument("--hourly-usd", type=float, default=0.69, help="check the provider's current price page")
    s.set_defaults(fn=cmd_gpu)
    return p


def main(argv: list[str] | None = None) -> None:
    import signal
    if hasattr(signal, "SIGPIPE"):  # `studio ... | head` should end quietly, not with a traceback
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    args = build_parser().parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

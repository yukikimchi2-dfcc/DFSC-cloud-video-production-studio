"""File-based render queue with retries, logs, progress, and chunk caching.

A job is a JSON file in <workspace>/queue/. It names a *timeline builder* — any importable
function `module:function(**kwargs) -> Timeline` — so jobs are reproducible from code + kwargs.

    job = enqueue("studio.render.demo:build_test_card", {"text": "TEST"}, mode="preview", name="demo")
    run_pending()   # or `studio queue run`

Chunked rendering: with `chunk_seconds`, the timeline is rendered in fixed-length silent chunks
cached under <workspace>/cache/chunks/<key>/, concatenated losslessly, then audio is muxed in.
Re-running a job reuses cached chunks; `invalidate=[(t0, t1)]` re-renders only chunks that
overlap those ranges (局部重新渲染).
"""
from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .. import versioning
from ..config import REPO_ROOT, load_config
from ..core.io import run_ffmpeg
from ..core.timeline import Timeline
from .renderer import Renderer, RenderResult, git_commit, loudnorm

STATES = ("queued", "running", "done", "failed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def workspace(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    return REPO_ROOT / cfg["studio"]["workspace_dir"]


def queue_dir(cfg: dict | None = None) -> Path:
    d = workspace(cfg) / "queue"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_builder(target: str):
    module, _, func = target.partition(":")
    if not func:
        raise ValueError(f"builder must look like 'package.module:function', got '{target}'")
    return getattr(importlib.import_module(module), func)


def enqueue(builder: str, kwargs: dict | None = None, mode: str = "preview", name: str | None = None,
            project_id: str | None = None, start: float = 0.0, end: float | None = None,
            chunk_seconds: float | None = None, invalidate: list | None = None, max_attempts: int = 3,
            upload: bool = False, cfg: dict | None = None) -> dict:
    job = {
        "id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
        "builder": builder, "kwargs": kwargs or {}, "mode": mode, "name": name, "project_id": project_id,
        "start": start, "end": end, "chunk_seconds": chunk_seconds, "invalidate": invalidate or [],
        "upload": upload, "state": "queued", "attempts": 0, "max_attempts": max_attempts,
        "progress": 0.0, "created_at": _now(), "history": [], "result": None, "error": None,
    }
    _save(job, cfg)
    return job


def _path(job_id: str, cfg=None) -> Path:
    return queue_dir(cfg) / f"{job_id}.json"


def _save(job: dict, cfg=None) -> None:
    tmp = _path(job["id"], cfg).with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_path(job["id"], cfg))


def load_job(job_id: str, cfg=None) -> dict:
    return json.loads(_path(job_id, cfg).read_text(encoding="utf-8"))


def list_jobs(cfg=None, state: str | None = None) -> list[dict]:
    jobs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(queue_dir(cfg).glob("*.json"))]
    return [j for j in jobs if state is None or j["state"] == state]


def _log(job: dict, msg: str, cfg=None) -> None:
    line = f"[{_now()}] {msg}"
    with open(queue_dir(cfg) / f"{job['id']}.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def chunk_key(job: dict, profile: dict, t0: float, t1: float) -> str:
    """Cache key for one chunk: builder + kwargs + render profile + time range + code version."""
    commit = (git_commit() or "nogit").removesuffix("-dirty")
    blob = json.dumps([job["builder"], job["kwargs"], profile, round(t0, 3), round(t1, 3), commit], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def render_chunked(timeline: Timeline, job: dict, renderer: Renderer, cfg: dict, progress=None) -> RenderResult:
    prof = renderer.profile(job["mode"])
    start = job["start"] or 0.0
    end = timeline.duration if job["end"] is None else min(job["end"], timeline.duration)
    step = float(job["chunk_seconds"])
    cache_root = workspace(cfg) / "cache" / "chunks"
    bounds = []
    t = start
    while t < end - 1e-6:
        bounds.append((t, min(t + step, end)))
        t += step
    stale = [tuple(r) for r in job.get("invalidate", [])]
    t_begin = time.time()
    with tempfile.TemporaryDirectory(prefix="studio-chunks-") as tmp:
        tmp = Path(tmp)
        listing = []
        for i, (c0, c1) in enumerate(bounds):
            cdir = cache_root / chunk_key(job, prof, c0, c1)
            cfile = cdir / "chunk.mp4"
            if any(c0 < r1 and r0 < c1 for r0, r1 in stale) and cfile.exists():
                cfile.unlink()
            if not cfile.exists():
                cdir.mkdir(parents=True, exist_ok=True)
                part = cdir / "chunk.partial.mp4"
                timeline.render(part, prof["width"], prof["height"], start=c0, end=c1, crf=int(prof["crf"]),
                                preset=prof.get("preset", "medium"))
                part.replace(cfile)
                job.setdefault("chunks_rendered", []).append([c0, c1])
            else:
                job.setdefault("chunks_cached", []).append([c0, c1])
            listing.append(f"file '{cfile}'")
            if progress:
                progress(i + 1, len(bounds))
        (tmp / "list.txt").write_text("\n".join(listing), encoding="utf-8")
        video = tmp / "video.mp4"
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"), "-c", "copy", str(video)])
        final = video
        audio_info = {}
        if timeline.audio:
            muxed = tmp / "muxed.mp4"
            run_ffmpeg(["-i", str(video), "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(timeline.audio),
                        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                        "-b:a", prof.get("audio_bitrate", "192k"), "-shortest", str(muxed)])
            final = muxed
            if job["mode"] == "final" and "loudness_lufs" in prof:
                normed = tmp / "normed.mp4"
                audio_info = loudnorm(muxed, normed, prof["loudness_lufs"], prof["true_peak_dbtp"],
                                      bitrate=prof.get("audio_bitrate", "256k"))
                final = normed
        out = versioning.reserve_output(renderer.out_dir, job["name"] or renderer.project_id or "untitled", job["mode"])
        shutil.move(str(final), out)
    from ..core.io import probe
    info = probe(out)
    result = RenderResult(path=str(out), mode=job["mode"], version=versioning.parse(out)["version"],
                          width=info.width, height=info.height, fps=timeline.fps, duration=info.duration,
                          size_mb=round(info.size_bytes / 1e6, 3), seconds=round(time.time() - t_begin, 2),
                          range=(start, end), crf=int(prof["crf"]), audio=audio_info, git_commit=git_commit(),
                          project_id=renderer.project_id, created_at=_now())
    renderer._record(result)
    return result


def run_job(job: dict, cfg: dict | None = None, uploader=None) -> dict:
    """Run one job with retries. `uploader(path, job) -> dict` is called on success when job.upload."""
    cfg = cfg or load_config(job.get("project_id"))
    while job["attempts"] < job["max_attempts"]:
        job["attempts"] += 1
        job["state"], job["started_at"] = "running", _now()
        _save(job, cfg)
        _log(job, f"attempt {job['attempts']}/{job['max_attempts']} builder={job['builder']} mode={job['mode']}", cfg)

        def progress(done, total):
            job["progress"] = round(done / total, 4)
            if done == total or done % 15 == 0:
                _save(job, cfg)

        try:
            timeline = resolve_builder(job["builder"])(**job["kwargs"])
            renderer = Renderer(job.get("project_id"), cfg)
            if job.get("chunk_seconds"):
                result = render_chunked(timeline, job, renderer, cfg, progress)
            else:
                result = renderer.render(timeline, job["mode"], job["name"], job["start"] or 0.0, job["end"],
                                         progress=progress)
            job["result"] = result.__dict__ | {"range": list(result.range)}
            if job.get("upload") and uploader:
                job["upload_result"] = uploader(result.path, job)
            job["state"], job["error"], job["finished_at"] = "done", None, _now()
            job["history"].append({"attempt": job["attempts"], "state": "done", "at": _now()})
            _log(job, f"done -> {result.path} ({result.size_mb} MB, {result.seconds}s)", cfg)
            _save(job, cfg)
            return job
        except Exception as e:  # noqa: BLE001 — every failure is logged and retried
            job["error"] = f"{type(e).__name__}: {e}"
            job["history"].append({"attempt": job["attempts"], "state": "failed", "error": job["error"], "at": _now()})
            _log(job, "FAILED " + job["error"] + "\n" + traceback.format_exc(), cfg)
            job["state"] = "queued" if job["attempts"] < job["max_attempts"] else "failed"
            _save(job, cfg)
            if job["state"] == "queued":
                time.sleep(min(2 ** job["attempts"], 30) * cfg.get("_retry_delay_scale", 1.0))
    return job


def run_pending(cfg: dict | None = None, uploader=None) -> list[dict]:
    return [run_job(j, cfg, uploader) for j in list_jobs(cfg, "queued")]

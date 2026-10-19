"""Cost guard for paid cloud GPU rendering.

Nothing in this repo may start a paid GPU unless ALL of these hold:
  1. config gpu.provider is not "none"
  2. env STUDIO_GPU_APPROVAL is set to an approval reference (who approved, when, budget)
  3. the job's estimated cost is within gpu.max_hourly_usd x estimated hours
Every decision (allowed or refused) is appended to workspace/gpu_decisions.jsonl.

CPU rendering (the default) is free inside the dev container; GPU mainly speeds up Whisper
transcription and very long final renders.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ..config import REPO_ROOT, load_config


class GpuNotApprovedError(PermissionError):
    pass


@dataclass
class GpuPlan:
    provider: str
    gpu_type: str
    hourly_usd: float
    est_hours: float
    auto_stop_minutes: int

    @property
    def est_cost_usd(self) -> float:
        # billed time includes the idle window before auto-stop kicks in
        return round(self.hourly_usd * (self.est_hours + self.auto_stop_minutes / 60), 2)


def estimate_render_hours(video_seconds: float, renders: int = 1, realtime_factor: float = 3.0,
                          transcribe_minutes: float = 0.0, whisper_speed: float = 20.0) -> float:
    """Rough wall-clock: render at `realtime_factor` x video length, Whisper at `whisper_speed` x realtime."""
    render_h = video_seconds * realtime_factor * renders / 3600
    whisper_h = transcribe_minutes / whisper_speed / 60
    return round(render_h + whisper_h, 3)


def check(plan: GpuPlan, cfg: dict | None = None) -> None:
    cfg = cfg or load_config()
    g = cfg["gpu"]
    approval = os.environ.get("STUDIO_GPU_APPROVAL")
    reasons = []
    if g["provider"] == "none":
        reasons.append("config gpu.provider is 'none'")
    if g.get("require_approval", True) and not approval:
        reasons.append("STUDIO_GPU_APPROVAL is not set (needs written approval from the budget owner)")
    if plan.hourly_usd > g["max_hourly_usd"]:
        reasons.append(f"hourly ${plan.hourly_usd} exceeds gpu.max_hourly_usd ${g['max_hourly_usd']}")
    _log(plan, approval, reasons)
    if reasons:
        raise GpuNotApprovedError("Paid GPU refused: " + "; ".join(reasons) +
                                  f". Estimated cost was ${plan.est_cost_usd}.")


def _log(plan: GpuPlan, approval: str | None, reasons: list[str]) -> None:
    path = REPO_ROOT / "workspace" / "gpu_decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "plan": asdict(plan),
           "est_cost_usd": plan.est_cost_usd, "approval": approval, "allowed": not reasons, "reasons": reasons}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

"""Intelligent segment selection: score transcript segments against story roles, build an EDL.

Roles: Hook, Storyline, Credibility, Pain Point, Solution, Benefits, CTA.
Scoring is pluggable — `KeywordScorer` works offline; `ClaudeScorer` asks Claude when
ANTHROPIC_API_KEY is set. Every EDL event keeps its source file and source in/out timecodes.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from .transcribe import Segment, Transcript

ROLES = ["Hook", "Storyline", "Credibility", "Pain Point", "Solution", "Benefits", "CTA"]

ROLE_KEYWORDS: dict[str, list[str]] = {
    "Hook": ["你知道", "為什麼", "为什么", "如果", "想像", "想象", "沒想到", "没想到", "第一次", "秘密", "竟然", "？", "?"],
    "Storyline": ["那時候", "那时候", "後來", "后来", "開始", "开始", "當時", "当时", "一路", "決定", "决定", "故事"],
    "Credibility": ["年", "得獎", "得奖", "冠軍", "冠军", "經驗", "经验", "成立", "客戶", "客户", "營收", "营收", "%", "萬", "万", "億", "亿"],
    "Pain Point": ["困難", "困难", "問題", "问题", "挑戰", "挑战", "失敗", "失败", "壓力", "压力", "不知道", "卡住", "焦慮", "焦虑"],
    "Solution": ["幫助", "帮助", "解決", "解决", "透過", "通过", "方法", "導師", "导师", "資源", "资源", "學到", "学到"],
    "Benefits": ["收穫", "收获", "改變", "改变", "成長", "成长", "機會", "机会", "連結", "连结", "人脈", "人脉", "值得"],
    "CTA": ["報名", "报名", "加入", "現在", "现在", "立即", "點擊", "点击", "截止", "一起", "參加", "参加", "連結", "链接"],
}


@dataclass
class EDLEvent:
    index: int
    role: str
    source: str
    src_in: float
    src_out: float
    text: str
    score: float
    rec_in: float = 0.0
    rec_out: float = 0.0
    reason: str = ""

    @property
    def duration(self) -> float:
        return self.src_out - self.src_in


@dataclass
class EDL:
    title: str
    fps: float = 30.0
    events: list[EDLEvent] = field(default_factory=list)
    goal: str = ""

    def relink(self) -> None:
        """Recompute record (output) timecodes from event order."""
        t = 0.0
        for i, e in enumerate(self.events, 1):
            e.index, e.rec_in, e.rec_out = i, t, t + e.duration
            t = e.rec_out

    @property
    def duration(self) -> float:
        return sum(e.duration for e in self.events)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EDL":
        return cls(d["title"], d.get("fps", 30.0), [EDLEvent(**e) for e in d.get("events", [])], d.get("goal", ""))

    def save(self, path: str | Path) -> Path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        return Path(path)

    @classmethod
    def load(cls, path: str | Path) -> "EDL":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_cmx3600(self) -> str:
        """CMX3600-style text EDL (reel = source file stem). For hand-off/review, not round-tripping."""
        lines = [f"TITLE: {self.title}", "FCM: NON-DROP FRAME", ""]
        for e in self.events:
            reel = re.sub(r"[^A-Za-z0-9_]", "_", Path(e.source).stem)[:8].upper() or "AX"
            lines.append(f"{e.index:03d}  {reel:<8} AA/V  C        "
                         f"{tc(e.src_in, self.fps)} {tc(e.src_out, self.fps)} {tc(e.rec_in, self.fps)} {tc(e.rec_out, self.fps)}")
            lines.append(f"* FROM CLIP NAME: {Path(e.source).name}")
            lines.append(f"* ROLE: {e.role} | {e.text[:60]}")
            lines.append("")
        return "\n".join(lines)


def tc(t: float, fps: float) -> str:
    frames = int(round(t * fps))
    f = frames % int(round(fps))
    s = frames // int(round(fps))
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


class Scorer(Protocol):
    def score(self, segments: list[Segment], goal: str) -> list[dict[str, float]]:
        """Return, per segment, a {role: score 0..1} dict."""


class KeywordScorer:
    """Offline heuristic: keyword hits per role, normalised, with light position priors."""

    def __init__(self, keywords: dict[str, list[str]] | None = None):
        self.keywords = keywords or ROLE_KEYWORDS

    def score(self, segments, goal=""):
        n = max(len(segments), 1)
        goal_terms = [g for g in re.split(r"[\s,，、]+", goal) if g]
        out = []
        for i, s in enumerate(segments):
            text = s.text
            scores = {}
            for role, kws in self.keywords.items():
                hits = sum(text.count(k) for k in kws)
                scores[role] = min(hits / 2.0, 1.0)
            pos = i / n
            scores["Hook"] += 0.1 * (len(text) <= 30)      # short punchy lines make good hooks
            scores["CTA"] += 0.15 * (pos > 0.7)
            scores["Storyline"] += 0.1 * (0.2 < pos < 0.8)
            goal_bonus = 0.2 * min(sum(text.count(g) for g in goal_terms), 2) / 2 if goal_terms else 0
            scores = {r: min(v + goal_bonus, 1.0) * s.confidence for r, v in scores.items()}
            out.append(scores)
        return out


class ClaudeScorer:
    """Ask Claude to score segments. Requires ANTHROPIC_API_KEY and the `anthropic` package."""

    MODEL = "claude-sonnet-5-5"
    PROMPT = (
        "你是一位資深廣告剪輯師。以下是一段訪談的逐字稿片段（每段有編號）。\n"
        "影片目標：{goal}\n"
        "請為每一段在下列角色中打分（0 到 1）：{roles}。\n"
        "只回傳 JSON：{{\"scores\": [{{\"id\": 0, \"Hook\": 0.2, ...}}, ...]}}，不要改寫內容。\n\n{segments}"
    )

    def __init__(self, model: str | None = None):
        self.model = model or self.MODEL

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def build_prompt(self, segments: list[Segment], goal: str) -> str:
        body = "\n".join(f"[{i}] ({s.start:.1f}-{s.end:.1f}s) {s.text}" for i, s in enumerate(segments))
        return self.PROMPT.format(goal=goal or "（未指定）", roles=", ".join(ROLES), segments=body)

    def score(self, segments, goal=""):
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(model=self.model, max_tokens=4096,
                                     messages=[{"role": "user", "content": self.build_prompt(segments, goal)}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        by_id = {int(d["id"]): d for d in data["scores"]}
        return [{r: float(by_id.get(i, {}).get(r, 0.0)) for r in ROLES} for i in range(len(segments))]


def select_segments(transcript: Transcript, goal: str = "", roles: list[str] | None = None,
                    per_role: int = 1, max_duration: float | None = None, min_score: float = 0.05,
                    scorer: Scorer | None = None, title: str | None = None, fps: float = 30.0,
                    pad: float = 0.08) -> EDL:
    """Pick the best segment(s) for each role (optimal one-to-one assignment), in story order."""
    roles = roles or ROLES
    segs = [s for s in transcript.segments if s.text.strip()]
    scorer = scorer or (ClaudeScorer() if ClaudeScorer.available() and _has_anthropic() else KeywordScorer())
    scores = scorer.score(segs, goal)
    # global assignment (Hungarian) so an early role can't steal the only good segment of a later one
    slots = [r for r in roles for _ in range(per_role)]
    picks: list[tuple[str, int, float]] = []
    if segs and slots:
        from scipy.optimize import linear_sum_assignment
        cost = -np.array([[scores[i].get(r, 0.0) for i in range(len(segs))] for r in slots])
        for ri, si in zip(*linear_sum_assignment(cost)):
            if -cost[ri, si] >= min_score:
                picks.append((slots[ri], int(si), float(-cost[ri, si])))
    if max_duration:
        # drop the weakest picks until the cut fits
        picks.sort(key=lambda p: -p[2])
        while picks and sum(segs[i].end - segs[i].start + 2 * pad for _, i, _ in picks) > max_duration:
            picks.pop()
    picks.sort(key=lambda p: (roles.index(p[0]), segs[p[1]].start))
    events = [EDLEvent(0, role, transcript.source, max(segs[i].start - pad, 0), segs[i].end + pad, segs[i].text,
                       round(sc, 3), reason=f"{type(scorer).__name__} score") for role, i, sc in picks]
    edl = EDL(title or Path(transcript.source).stem, fps, events, goal)
    edl.relink()
    return edl


def _has_anthropic() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False

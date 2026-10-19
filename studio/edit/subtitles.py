"""Subtitle engine: word-timed chunking, timing correction, SRT/ASS export and a burn-in layer.

Cues keep their Word objects, so the burn-in layer can highlight word by word.
Text is converted to Traditional Chinese (OpenCC when installed) unless disabled.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..config import get
from ..core.canvas import Patch, hex_to_rgb
from ..core.timeline import Layer, RenderContext
from .transcribe import Transcript, Word, srt_time, to_traditional

BREAK_PUNCT = set("，。！？；：、,.!?;:…")
HARD_PUNCT = set("。！？!?.…")
STRIP_PUNCT = "，。、；：,.;:"   # removed from display (Chinese subtitle convention); ！？ are kept


@dataclass
class Cue:
    start: float
    end: float
    lines: list[list[Word]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line_text(l) for l in self.lines)


def display(text: str) -> str:
    return text.strip().strip(STRIP_PUNCT).replace("，", " ").replace(",", " ").strip()


def line_text(words: list[Word]) -> str:
    return display("".join(w.text for w in words))


def _len(text: str) -> float:
    """Visual length: CJK = 1, ASCII = 0.55 (half width-ish)."""
    return sum(0.55 if ord(c) < 128 else 1.0 for c in text)


def chunk_words(words: list[Word], max_chars: int = 14, max_lines: int = 2, pause_break: float = 0.45,
                skip_fillers: bool = True, traditional: bool = True) -> list[Cue]:
    """Group words into cues of <= max_lines lines of <= max_chars visual characters.
    Lines break at punctuation, at pauses >= pause_break, or when full; cues end at hard
    punctuation, long pauses, or when max_lines is reached."""
    conv = to_traditional if traditional else (lambda s: s)
    ws = [Word(w.start, w.end, conv(w.text), w.confidence, w.speaker, w.is_filler)
          for w in words if not (skip_fillers and w.is_filler) and w.text.strip()]
    cues: list[Cue] = []
    lines: list[list[Word]] = []
    line: list[Word] = []

    def flush_line():
        nonlocal line
        if line:
            lines.append(line)
            line = []

    def flush_cue():
        nonlocal lines
        flush_line()
        if lines:
            cues.append(Cue(lines[0][0].start, lines[-1][-1].end, lines))
            lines = []

    for i, w in enumerate(ws):
        if line and _len(line_text(line + [w])) > max_chars:
            flush_line()
            if len(lines) >= max_lines:
                flush_cue()
        line.append(w)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        gap = (nxt.start - w.end) if nxt else 0
        last_char = w.text.strip()[-1:]
        if nxt is None or last_char in HARD_PUNCT or gap >= pause_break * 2:
            flush_cue()
        elif last_char in BREAK_PUNCT or gap >= pause_break:
            flush_line()
            if len(lines) >= max_lines:
                flush_cue()
    flush_cue()
    return cues


def fix_timing(cues: list[Cue], min_duration: float = 0.7, max_duration: float = 6.0, min_gap: float = 0.04,
               lead_in: float = 0.05) -> list[Cue]:
    """Ensure readable durations and no overlaps (in place; also returns the list)."""
    for c in cues:
        c.start = max(c.start - lead_in, 0.0)
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else None
        if c.end - c.start < min_duration:
            c.end = c.start + min_duration
        c.end = min(c.end, c.start + max_duration)
        if nxt is not None and c.end > nxt - min_gap:
            c.end = max(nxt - min_gap, c.start + 0.1)
    for i in range(1, len(cues)):
        if cues[i].start < cues[i - 1].end + min_gap:
            cues[i].start = cues[i - 1].end + min_gap
    return cues


def cues_from_transcript(transcript: Transcript, cfg: dict | None = None, **kw) -> list[Cue]:
    cfg = cfg or {}
    cues = chunk_words(transcript.words, max_chars=kw.pop("max_chars", get(cfg, "subtitles.max_chars_per_line", 14)),
                       max_lines=kw.pop("max_lines", get(cfg, "subtitles.max_lines", 2)),
                       traditional=kw.pop("traditional", get(cfg, "subtitles.script", "traditional") == "traditional"),
                       **kw)
    return fix_timing(cues)


def to_srt(cues: list[Cue]) -> str:
    return "\n".join(f"{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1))


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_color(hex_color: str) -> str:
    r, g, b = (int(round(c * 255)) for c in hex_to_rgb(hex_color))
    return f"&H00{b:02X}{g:02X}{r:02X}"


def to_ass(cues: list[Cue], width: int = 1080, height: int = 1920, font: str = "Noto Sans CJK TC",
           size: int = 72, color: str = "#FFFFFF", highlight: str = "#47B649", outline: str = "#000000",
           margin_v: int = 380, karaoke: bool = True) -> str:
    """ASS with optional \\k karaoke timing (highlight colour = SecondaryColour sweep)."""
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{size},{_ass_color(highlight) if karaoke else _ass_color(color)},{_ass_color(color)},"
        f"{_ass_color(outline)},&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,60,60,{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    for c in cues:
        if karaoke:
            parts = []
            for li, line in enumerate(c.lines):
                for w in line:
                    parts.append(f"{{\\k{max(int(round((w.end - w.start) * 100)), 1)}}}{display(w.text)}")
                if li < len(c.lines) - 1:
                    parts.append("\\N")
            text = "".join(parts)
        else:
            text = c.text.replace("\n", "\\N")
        events.append(f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Default,,0,0,0,,{text}")
    return head + "\n".join(events) + "\n"


def write_subtitles(cues: list[Cue], out_base: str | Path, **ass_kw) -> tuple[Path, Path]:
    base = Path(out_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    srt, ass = base.with_suffix(".srt"), base.with_suffix(".ass")
    srt.write_text(to_srt(cues), encoding="utf-8")
    ass.write_text(to_ass(cues, **ass_kw), encoding="utf-8")
    return srt, ass


class SubtitleLayer(Layer):
    """Burn-in subtitles with word-by-word highlight, stroke and soft shadow.

    Cue times are relative to the layer start. Sizes are design-space (1080x1920) pixels.
    The block is centred horizontally and sits on the bottom edge of the safe area
    (or at `y` if given, as the block's bottom edge)."""

    def __init__(self, cues: list[Cue], size: int = 68, color: str = "text", highlight: str | None = "primary",
                 stroke: str = "#000000", stroke_width: int = 6, shadow: float = 0.45, line_spacing: float = 1.25,
                 y: float | None = None, font_role: str = "subtitle", pop: bool = True, **kw):
        super().__init__(**kw)
        self.cues, self.size, self.color, self.highlight = cues, size, color, highlight
        self.stroke, self.stroke_width, self.shadow, self.line_spacing = stroke, stroke_width, shadow, line_spacing
        self.y, self.font_role, self.pop = y, font_role, pop
        self._cache: dict = {}
        self.last_box: tuple[int, int, int, int] | None = None   # for QC (x0, y0, x1, y1)

    def _col(self, ctx: RenderContext, key: str) -> tuple[int, int, int]:
        c = ctx.brand.color(key) if (ctx.brand and not key.startswith("#")) else (key if key.startswith("#") else "#FFFFFF")
        return tuple(int(round(v * 255)) for v in hex_to_rgb(c))

    def active_cue(self, t: float) -> Cue | None:
        for c in self.cues:
            if c.start <= t < c.end:
                return c
        return None

    def _render_cue(self, ctx: RenderContext, cue: Cue, active_idx: int) -> Image.Image:
        from ..brand import BrandKit
        brand = ctx.brand or BrandKit.neutral()
        size, sw = ctx.px(self.size), max(ctx.px(self.stroke_width), 1)
        font = brand.font(self.font_role, size)
        base, hi, stroke = self._col(ctx, self.color), self._col(ctx, self.highlight or self.color), self._col(ctx, self.stroke)
        # (token, global word index) — punctuation-only words are not drawn but keep their index
        lines, k = [], 0
        for line in cue.lines:
            toks = []
            for w in line:
                if display(w.text):
                    toks.append((display(w.text), k))
                k += 1
            lines.append(toks)
        widths = [sum(font.getlength(tok) for tok, _ in line) for line in lines]
        lh = int(size * self.line_spacing)
        pad = sw * 2 + ctx.px(16)
        W, H = int(max(widths, default=1)) + 2 * pad, lh * len(lines) + 2 * pad
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for li, line in enumerate(lines):
            x = pad + (W - 2 * pad - widths[li]) / 2
            y = pad + li * lh
            for tok, idx in line:
                fill = hi if (self.highlight and idx <= active_idx) else base
                draw.text((x, y), tok, font=font, fill=fill + (255,), stroke_width=sw, stroke_fill=stroke + (255,))
                x += font.getlength(tok)
        if self.shadow > 0:
            a = img.split()[3].filter(ImageFilter.GaussianBlur(ctx.px(10)))
            sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
            sh.putalpha(a.point(lambda v: int(v * self.shadow)))
            sh = sh.transform(sh.size, Image.AFFINE, (1, 0, 0, 0, 1, -ctx.px(6)))
            img = Image.alpha_composite(sh, img)
        return img

    def render(self, ctx, t):
        cue = self.active_cue(t)
        if cue is None:
            self.last_box = None
            return None
        words = [w for line in cue.lines for w in line]
        active = max((i for i, w in enumerate(words) if t >= w.start), default=-1)
        key = (id(cue), active, ctx.width, ctx.height)
        if key not in self._cache:
            if len(self._cache) > 64:
                self._cache.clear()
            self._cache[key] = np.asarray(self._render_cue(ctx, cue, active), np.float32) / 255
        rgba = self._cache[key]
        h, w = rgba.shape[:2]
        x0, y0, x1, y1 = ctx.safe_rect()
        bottom = ctx.px(self.y) if self.y is not None else y1
        if self.pop and t - cue.start < 0.12:      # quick settle-in: slide up 12 design px
            bottom += ctx.px(12 * (1 - (t - cue.start) / 0.12))
        x = (ctx.width - w) // 2
        y = int(bottom - h)
        self.last_box = (x, y, x + w, y + h)
        return Patch(rgba, x, y)

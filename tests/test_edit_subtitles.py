import numpy as np

from fixtures import make_transcript
from studio.brand import BrandKit
from studio.core.timeline import Timeline
from studio.edit import subtitles as st
from studio.edit.transcribe import mark_fillers


def cues():
    t = make_transcript()
    mark_fillers(t)
    return st.cues_from_transcript(t, {"subtitles": {"max_chars_per_line": 8, "max_lines": 2, "script": "traditional"}})


def test_chunking_limits_and_traditional():
    cs = cues()
    assert cs
    for c in cs:
        assert len(c.lines) <= 2
        for line in c.lines:
            assert st._len(st.line_text(line)) <= 8 or len(line) == 1
    text = "".join(c.text for c in cs)
    assert "嗯" not in text                       # fillers skipped
    assert "，" not in text and "。" not in text    # punctuation stripped for display
    try:
        import opencc  # noqa: F401
        assert "為什麼" in text and "報名" in text
    except ImportError:
        pass


def test_timing_no_overlap_min_duration():
    cs = cues()
    for a, b in zip(cs, cs[1:]):
        assert a.end <= b.start - 0.039
    assert all(c.end - c.start >= 0.1 for c in cs)
    short = [st.Cue(0.0, 0.1, []), st.Cue(0.2, 0.5, [])]
    st.fix_timing(short, min_duration=0.7, lead_in=0)
    assert short[0].end <= short[1].start


def test_srt_and_ass(tmp_path):
    srt, ass = st.write_subtitles(cues(), tmp_path / "subs")
    s = srt.read_text(encoding="utf-8")
    assert "-->" in s
    a = ass.read_text(encoding="utf-8")
    assert "[Events]" in a and "\\k" in a and "Dialogue:" in a


def test_subtitle_layer_renders_inside_safe_area():
    cs = cues()
    layer = st.SubtitleLayer(cs, size=64)
    tl = Timeline(540, 960, 25, cs[-1].end + 0.5, background="#202020", brand=BrandKit.neutral()).add(layer)
    ctx = tl.context()
    t = (cs[0].start + cs[0].end) / 2 + 0.2
    frame = tl.render_frame(t, ctx)
    assert layer.last_box is not None
    x0, y0, x1, y1 = layer.last_box
    sx0, sy0, sx1, sy1 = ctx.safe_rect()
    assert y1 <= sy1 and x0 >= 0 and x1 <= ctx.width
    region = frame[y0:y1, x0:x1]
    assert region.max() > 0.9                    # white text drawn
    empty = tl.render_frame(cs[-1].end + 0.3, ctx)
    assert np.allclose(empty, empty[0, 0])       # no cue -> nothing drawn


def test_word_highlight_changes_over_time():
    cs = cues()
    c = cs[0]
    layer = st.SubtitleLayer(cs, size=64, highlight="#FF0000")
    tl = Timeline(540, 960, 25, 5, brand=BrandKit.neutral()).add(layer)
    ctx = tl.context()
    words = [w for line in c.lines for w in line]
    early = tl.render_frame(words[0].start + 0.15, ctx)
    late = tl.render_frame(words[-1].start + 0.01, ctx)
    red = lambda f: int(((f[..., 0] > 0.8) & (f[..., 1] < 0.3)).sum())  # noqa: E731
    assert red(late) > red(early) > 0

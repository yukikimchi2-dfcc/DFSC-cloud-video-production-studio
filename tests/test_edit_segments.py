from fixtures import make_transcript
from studio.edit.segments import EDL, ClaudeScorer, KeywordScorer, select_segments


def test_select_by_role_keeps_source_timecodes(tmp_path):
    t = make_transcript("interview_A.mp4")
    edl = select_segments(t, goal="创业 报名", scorer=KeywordScorer())
    roles = [e.role for e in edl.events]
    assert roles[0] == "Hook" and "CTA" in roles
    by_role = {e.role: e for e in edl.events}
    assert "报名" in by_role["CTA"].text
    assert "困难" in by_role["Pain Point"].text
    seg_bounds = [(s.start, s.end) for s in t.segments]
    for e in edl.events:
        assert e.source == "interview_A.mp4"
        assert any(abs(e.src_in - max(a - 0.08, 0)) < 1e-6 and abs(e.src_out - (b + 0.08)) < 1e-6 for a, b in seg_bounds)
    assert len({e.text for e in edl.events}) == len(edl.events)   # no segment reused
    assert abs(edl.events[-1].rec_out - edl.duration) < 1e-6
    back = EDL.load(edl.save(tmp_path / "e.json"))
    assert back.to_dict() == edl.to_dict()


def test_max_duration_and_cmx():
    t = make_transcript("clip.mov")
    edl = select_segments(t, max_duration=5.0, scorer=KeywordScorer())
    assert edl.duration <= 5.0
    cmx = edl.to_cmx3600()
    assert cmx.startswith("TITLE: clip") and "FROM CLIP NAME: clip.mov" in cmx


def test_claude_prompt_built_without_calling_api():
    t = make_transcript()
    prompt = ClaudeScorer().build_prompt(t.segments, "招生广告")
    assert "招生广告" in prompt and "[4]" in prompt and "CTA" in prompt


def test_padding_never_makes_adjacent_picks_overlap():
    """Regression (found on a real interview): 0.08 s padding crossed a 40 ms gap between sentences."""
    from studio.edit.segments import select_segments
    from studio.edit.transcribe import Segment, Transcript, Word
    texts = ["創業最重要的是開始", "我的專案是氣球", "歡迎大家來參加報名"]
    segs, t = [], 0.0
    for txt in texts:
        segs.append(Segment(t, t + 2.0, txt, [Word(t, t + 2.0, txt)]))
        t += 2.04                                   # 40 ms gaps
    edl = select_segments(Transcript("x.mp4", "zh", segs), goal="招生", roles=["Hook", "Storyline", "CTA"])
    spans = sorted((e.src_in, e.src_out) for e in edl.events)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), spans

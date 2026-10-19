import shutil

import pytest

from studio import project as P
from studio.config import PROJECTS_DIR, load_yaml
from studio.gpu.guard import GpuNotApprovedError, GpuPlan, check, estimate_render_hours


@pytest.fixture
def proj():
    pid = "zz-test-project"
    shutil.rmtree(PROJECTS_DIR / pid, ignore_errors=True)
    P.create_project(pid, "測試專案", brand_from="dfsc-2027", owner="tester")
    yield pid
    shutil.rmtree(PROJECTS_DIR / pid, ignore_errors=True)


def test_create_copies_brand_without_source_and_refuses_overwrite(proj):
    d = P.project_dir(proj)
    assert (d / "brand" / "brand.yaml").exists() and not (d / "brand" / "source").exists()
    assert (d / "HANDOVER.md").exists()
    with pytest.raises(FileExistsError):
        P.create_project(proj, "again")


def test_status_workflow_and_role_permissions(proj):
    P.set_status(proj, "In Progress", "ed", "Editor")
    P.set_status(proj, "Awaiting Review", "ed", "Editor")
    with pytest.raises(P.PermissionDenied, match="cannot 'approve'"):
        P.set_status(proj, "Approved", "ed", "Editor")
    with pytest.raises(P.PermissionDenied, match="not a valid step"):
        P.set_status(proj, "Completed", "rev", "Reviewer")
    P.set_status(proj, "Revision Required", "rev", "Reviewer", note="字幕太小")
    P.set_status(proj, "In Progress", "ed", "Editor")
    P.set_status(proj, "Awaiting Review", "ed", "Editor")
    P.set_status(proj, "Approved", "rev", "Reviewer")
    P.set_status(proj, "Completed", "rev", "Reviewer")
    with pytest.raises(P.PermissionDenied, match="only Admin"):
        P.set_status(proj, "Archived", "rev", "Reviewer")
    with pytest.raises(P.PermissionDenied):
        P.set_status(proj, "Archived", "v", "Viewer")
    P.set_status(proj, "Archived", "boss", "Admin")
    assert load_yaml(P.project_dir(proj) / "project.yaml")["status"] == "Archived"
    events = [r for r in P.activity(proj) if r["event"] == "status"]
    assert len(events) == 8 and events[2]["detail"]["note"] == "字幕太小"


def test_handover_contains_everything_a_new_editor_needs(proj):
    P.update_handover_fields(proj, todo=["換配樂"], known_issues=["第 12 秒字幕壓到臉"], next_action="提交審核",
                             assets=["interview_A.mp4"], templates=["title_card_impact@1.0"])
    text = (P.project_dir(proj) / "HANDOVER.md").read_text(encoding="utf-8")
    for needle in ("当前状态", "換配樂", "第 12 秒字幕壓到臉", "提交審核", "interview_A.mp4",
                   "title_card_impact@1.0", "最近一次渲染", "代码版本"):
        assert needle in text


def test_gpu_guard_refuses_without_approval(monkeypatch):
    monkeypatch.delenv("STUDIO_GPU_APPROVAL", raising=False)
    plan = GpuPlan("runpod", "RTX 4090", 0.69, estimate_render_hours(60, 3), 15)
    assert plan.est_cost_usd > 0
    with pytest.raises(GpuNotApprovedError, match="provider is 'none'"):
        check(plan)

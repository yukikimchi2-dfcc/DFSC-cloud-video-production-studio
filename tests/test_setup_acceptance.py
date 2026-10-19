"""Setup acceptance tests from the brief (第九阶段): run before declaring setup complete."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from studio.audit import run_audit
from studio.config import REPO_ROOT


# ---- Test 1 — Cloud Environment -------------------------------------------------
def test_1_cloud_environment_has_toolchain():
    a = run_audit(check_network=False)
    assert a["tools"]["ffmpeg"]["path"] and a["tools"]["ffprobe"]["path"]
    assert a["fonts"]["cjk_traditional"], "Noto Sans CJK TC missing — run the session-start hook / Dockerfile"
    missing = [k for k, v in a["python_packages"].items() if v is None and k != "pytest"]
    assert not missing, f"missing python packages: {missing}"
    on_cloud = a["cloud_session"]["claude_code_remote"] or a["cloud_session"]["codespaces"] or a["cloud_session"]["ci"]
    if not on_cloud:
        pytest.skip("not running in a cloud session (local machine) — toolchain OK")


# ---- Test 2 — GitHub -------------------------------------------------------------
def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def test_2_git_commit_read_update_restore(tmp_path):
    """Exercise commit / read / update / restore on a scratch clone (the real push is done by CI/session)."""
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO_ROOT), str(clone)], check=True)
    _git(clone, "config", "user.email", "studio-test@example.invalid")
    _git(clone, "config", "user.name", "studio test")
    f = clone / "SETUP_TEST.txt"
    f.write_text("v1\n")
    _git(clone, "add", str(f))
    _git(clone, "commit", "-qm", "setup test v1")
    v1 = _git(clone, "rev-parse", "HEAD")
    f.write_text("v2\n")
    _git(clone, "commit", "-qam", "setup test v2")
    assert _git(clone, "show", f"{v1}:SETUP_TEST.txt") == "v1"     # read old version
    _git(clone, "revert", "--no-edit", "HEAD")                                          # restore without rewriting history
    assert f.read_text() == "v1\n"
    assert len(_git(clone, "log", "--oneline").splitlines()) >= 3


def test_2_remote_is_configured():
    remote = _git(REPO_ROOT, "remote", "get-url", "origin")
    assert "DFSC-cloud-video-production-studio" in remote


# ---- Test 3 — Google Drive ---------------------------------------------------------
# Accepted separately:
#   3a  public read from this runtime (no credentials)
#   3b  write from THIS runtime — needs a Google identity here (OAuth token / service account /
#       connected Drive connector). The folders themselves are shared anyone:writer, so folder
#       permission is not the blocker; Google rejects anonymous writes with 401.
#   3c  a file uploaded from another client (ChatGPT Drive connector, 2026-10-19) is visible and
#       readable from this runtime — proves cross-client round trip, NOT this runtime's write path.
CROSS_CLIENT_TEST_FILE = "1IxNFMiIqOjUCycT_hv54nZAZ1eFnn5Sp"
@pytest.mark.network
def test_3a_drive_public_read_lists_reference_folders():
    import gdown
    from studio.config import PROJECTS_DIR, load_yaml
    url = load_yaml(PROJECTS_DIR / "dfsc-2027" / "project.yaml")["drive"]["reference_folders"][0]
    try:
        items = gdown.download_folder(url=url, skip_download=True, quiet=True)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"BLOCKED: public Drive folder not reachable from this environment ({type(e).__name__})")
    assert items and all(it.id for it in items)


@pytest.mark.network
def test_3c_cross_client_upload_is_readable_here(tmp_path):
    import gdown
    try:
        path = gdown.download(id=CROSS_CLIENT_TEST_FILE, output=str(tmp_path / "x.txt"), quiet=True)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"BLOCKED: Drive not reachable from this environment ({type(e).__name__})")
    assert path and "Cloud Video Production Studio" in open(path, encoding="utf-8").read()


@pytest.mark.network
def test_3_drive_read_write_verify(tmp_path):
    folder = os.environ.get("STUDIO_DRIVE_TEST_FOLDER")
    if not (os.environ.get("STUDIO_DRIVE_CREDENTIALS") or os.environ.get("STUDIO_DRIVE_TOKEN")) or not folder:
        pytest.skip("BLOCKED (3b write from this runtime): no Google identity in this runtime "
                    "(STUDIO_DRIVE_TOKEN / STUDIO_DRIVE_CREDENTIALS) — folder permission is anyone:writer; see docs/zh/03_Google_Drive_连接.md")
    from studio.cli import _drive_check
    from studio.storage.drive import DriveStore
    result = _drive_check(DriveStore(), folder)
    assert result["write"]["md5"] and result["download_verified"]


def test_3_drive_logic_against_local_store(tmp_path):
    """Same code path as Test 3, on the filesystem backend, so the logic is proven before credentials arrive."""
    from studio.cli import _drive_check
    from studio.storage.local import LocalStore
    store = LocalStore(tmp_path / "drive")
    store.create_folder("", "inbox")
    result = _drive_check(store, "inbox")
    assert result["download_verified"] and result["write"]["md5"]

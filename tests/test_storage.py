import os

import pytest

from studio.storage import STUDIO_STRUCTURE, ensure_structure, md5_file
from studio.storage.base import IntegrityError, RemoteFile, verify
from studio.storage.index import AssetIndex
from studio.storage.local import LocalStore


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path / "drive")


def test_ensure_structure_is_idempotent_and_keeps_existing(store):
    # simulate a pre-existing folder with the client's own content
    store.create_folder("", "Cloud Video Production Studio")
    store.create_folder("Cloud Video Production Studio", "01_Brand_Library")
    (store.root / "Cloud Video Production Studio/01_Brand_Library/old_logo.png").write_bytes(b"x")
    ids, report = ensure_structure(store, "")
    assert ("exists", "01_Brand_Library", "Cloud Video Production Studio/01_Brand_Library") in report
    n_expected = 1 + len(STUDIO_STRUCTURE) + sum(len(v) for v in STUDIO_STRUCTURE.values())
    assert len(ids) == n_expected
    _, again = ensure_structure(store, "")
    assert all(status == "exists" for status, *_ in again)   # second run creates nothing
    assert (store.root / "Cloud Video Production Studio/01_Brand_Library/old_logo.png").exists()


def test_upload_never_overwrites_and_verifies(store, tmp_path):
    f = tmp_path / "clip.txt"
    f.write_text("v1")
    a = store.upload(f, "")
    f.write_text("v2")
    b = store.upload(f, "")
    assert (a.name, b.name) == ("clip.txt", "clip (2).txt")
    assert (store.root / "clip.txt").read_text() == "v1"
    dl = store.download(b.id, tmp_path / "dl" / "x.txt")
    assert dl.read_text() == "v2"


def test_md5_mismatch_raises(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    with pytest.raises(IntegrityError):
        verify(f, RemoteFile("id", "a.bin", "application/octet-stream", md5="0" * 32))
    verify(f, RemoteFile("id", "a.bin", "application/octet-stream", md5=md5_file(f)))


def test_index_batches_tracks_changes_and_keeps_annotations(store, tmp_path):
    for i in range(5):
        (store.root / f"v{i}.mp4").write_bytes(os.urandom(64))
    idx = AssetIndex(tmp_path / "index.jsonl")
    first = idx.scan(store, "", batch_size=3, brand="dfsc-2027")
    assert first["new"] == 3 and first.get("batch_limit_reached")
    second = idx.scan(store, "", batch_size=3)
    assert second["new"] == 2 and second["unchanged"] == 3
    key = "local:v0.mp4"
    idx.annotate(key, purpose="interview", review_status="APPROVED")
    (store.root / "v0.mp4").write_bytes(b"changed")
    third = AssetIndex(tmp_path / "index.jsonl").scan(store, "")
    assert third["changed"] == 1
    reloaded = AssetIndex(tmp_path / "index.jsonl")
    e = reloaded.entries[key]
    assert e["purpose"] == "interview" and e["review_status"] == "APPROVED" and e["brand"] == "dfsc-2027"
    assert len(e["previous_versions"]) == 1
    assert reloaded.summary()["by_kind"] == {"video": 5}
    with pytest.raises(ValueError):
        reloaded.annotate(key, md5="hack")


def test_drive_query_escaping():
    from studio.storage.drive import _q_escape
    assert _q_escape("Bob's \\ folder") == "Bob\\'s \\\\ folder"


def test_drive_without_credentials_gives_actionable_error(monkeypatch):
    from studio.storage.drive import OAUTH_ENV, DriveUnavailableError, _credentials
    for k in ("STUDIO_DRIVE_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS", "STUDIO_DRIVE_TOKEN", *OAUTH_ENV):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(DriveUnavailableError, match="STUDIO_DRIVE_OAUTH_REFRESH_TOKEN"):
        _credentials()

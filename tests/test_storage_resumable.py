"""Resumable uploader against a local fake Drive endpoint (no Google, no credentials)."""
import hashlib
import os

import pytest
import requests

from studio.storage.resumable import ResumableUploader, UploadError
from fake_drive_upload import FakeDrive

CHUNK = 256 * 1024


@pytest.fixture
def fake():
    f = FakeDrive()
    yield f
    f.close()


@pytest.fixture
def blob(tmp_path):
    p = tmp_path / "clip.mp4"
    p.write_bytes(os.urandom(5 * CHUNK + 1234))   # not a chunk multiple: exercises the short last chunk
    return p


def _uploader(fake, tmp_path, **kw):
    return ResumableUploader(requests.Session(), tmp_path / "state", base_url=fake.base_url,
                             chunk_size=CHUNK, backoff=0.0, **kw)


def test_uploads_in_chunks_and_md5_matches(fake, blob, tmp_path):
    md = _uploader(fake, tmp_path).upload(blob, "folder123")
    assert md["md5Checksum"] == hashlib.md5(blob.read_bytes()).hexdigest()
    assert md["parents"] == ["folder123"] and int(md["size"]) == blob.stat().st_size
    assert fake.put_count == 6
    assert not list((tmp_path / "state").glob("*.json"))          # state cleaned up on success


def test_resumes_after_crash_without_resending(fake, blob, tmp_path):
    up = _uploader(fake, tmp_path)
    with pytest.raises(UploadError, match="simulated interruption"):
        up.upload(blob, "f", stop_after_chunks=3)
    assert len(list((tmp_path / "state").glob("*.json"))) == 1     # session URI persisted
    puts_before = fake.put_count
    md = _uploader(fake, tmp_path).upload(blob, "f")               # new process, same state dir
    assert md["md5Checksum"] == hashlib.md5(blob.read_bytes()).hexdigest()
    assert fake.put_count - puts_before == 3                       # only the remaining 3 chunks
    assert len(fake.sessions) == 1                                  # same session reused


def test_retries_transient_503(fake, blob, tmp_path):
    fake.fail_puts = {2, 3}
    md = _uploader(fake, tmp_path).upload(blob, "f")
    assert md["md5Checksum"] == hashlib.md5(blob.read_bytes()).hexdigest()


def test_expired_session_starts_over(fake, blob, tmp_path):
    with pytest.raises(UploadError):
        _uploader(fake, tmp_path).upload(blob, "f", stop_after_chunks=2)
    fake.expire_all()
    md = _uploader(fake, tmp_path).upload(blob, "f")
    assert md["md5Checksum"] == hashlib.md5(blob.read_bytes()).hexdigest()


def test_chunk_size_must_be_256k_multiple(tmp_path):
    with pytest.raises(ValueError):
        ResumableUploader(requests.Session(), tmp_path, chunk_size=1000)


def test_oauth_env_credentials_are_built_without_printing(monkeypatch):
    from studio.storage import drive
    for k, v in zip(drive.OAUTH_ENV, ("cid.apps.googleusercontent.com", "s3cr3t", "1//refresh")):
        monkeypatch.setenv(k, v)
    assert drive.credential_source() == "oauth_env"
    creds = drive._credentials()
    assert creds.refresh_token == "1//refresh" and creds.token_uri == drive.TOKEN_URI
    assert "https://www.googleapis.com/auth/drive" in creds.scopes

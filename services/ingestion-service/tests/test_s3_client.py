"""Regression tests for upload_local's path-traversal containment check.

file.filename in the upload endpoint is client-supplied and untrusted; before
routers/upload.py strips it to a basename, upload_local() must independently
refuse to write outside its configured storage root — belt and suspenders.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ingestion_service import config as _cfg
from ingestion_service.s3_client import upload_local


@pytest.fixture()
def storage_root(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(_cfg.settings, "local_storage_path", str(root))
    return root


def test_upload_local_writes_legitimate_key(storage_root):
    key = "stubs/proj-1/stub-1/source/payment.txt"
    upload_local(key, b"hello")
    assert (storage_root / key).read_bytes() == b"hello"


def test_upload_local_rejects_parent_traversal(storage_root):
    # One level of ".." from the root always escapes it, regardless of how
    # deeply nested tmp_path/storage_root happens to be on this machine.
    with pytest.raises(ValueError):
        upload_local("../evil.txt", b"pwned")
    assert not (storage_root.parent / "evil.txt").exists()


def test_upload_local_rejects_absolute_path_escape(storage_root):
    outside = str(Path(storage_root).parent / "evil.txt")
    with pytest.raises(ValueError):
        upload_local(outside, b"pwned")
    assert not Path(outside).exists()

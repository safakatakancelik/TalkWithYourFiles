import hashlib
import io
from pathlib import Path

import pytest

from twyf.files.store import save
from twyf.services.errors import ServiceError


def test_store_named_by_hash(tmp_path: Path) -> None:
    data = b"hello world"
    sha = hashlib.sha256(data).hexdigest()
    got_sha, size, location = save(tmp_path, io.BytesIO(data), 1000)
    assert (got_sha, size) == (sha, len(data))
    assert location == Path("files") / sha[:2] / sha
    assert (tmp_path / location).read_bytes() == data
    save(tmp_path, io.BytesIO(data), 1000)
    stored = [p for p in (tmp_path / "files").rglob("*") if p.is_file()]
    assert stored == [tmp_path / location]


def test_store_rejects_oversize(tmp_path: Path) -> None:
    with pytest.raises(ServiceError) as raised:
        save(tmp_path, io.BytesIO(b"x" * 101), 100)
    assert raised.value.code == "too_large"
    assert [p for p in (tmp_path / "files").rglob("*") if p.is_file()] == []


def test_store_keeps_existing_copy(tmp_path: Path) -> None:
    _, _, location = save(tmp_path, io.BytesIO(b"abc"), 100)
    before = (tmp_path / location).stat().st_mtime_ns
    save(tmp_path, io.BytesIO(b"abc"), 100)
    assert (tmp_path / location).stat().st_mtime_ns == before

"""Keeps uploaded bytes in the data folder, named by their SHA-256. Never overwrites and never removes a stored file."""

import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from twyf.services.errors import ServiceError

CHUNK = 1024 * 1024


def location_for(sha256: str) -> Path:
    """The path under the data folder: files/<first two hex>/<sha256>."""
    return Path("files") / sha256[:2] / sha256


def save(data_dir: Path, stream: BinaryIO, max_bytes: int) -> tuple[str, int, Path]:
    """Streams to a temporary file while hashing, then moves it into place. Returns (sha256, size, location)."""
    files = data_dir / "files"
    files.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    fd, tmp_name = tempfile.mkstemp(dir=files, prefix=".upload-")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            while block := stream.read(CHUNK):
                size += len(block)
                if size > max_bytes:
                    raise ServiceError("too_large", f"The file is larger than {max_bytes // (1024 * 1024)} MB")
                digest.update(block)
                out.write(block)
        sha = digest.hexdigest()
        location = location_for(sha)
        target = data_dir / location
        if target.exists():
            tmp.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(tmp, target)  # fails rather than replace a file that appeared meanwhile
            tmp.unlink()
        return sha, size, location
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

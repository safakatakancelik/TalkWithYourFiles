import json
import os
from pathlib import Path

import pytest

from twyf.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("TWYF_"):
            monkeypatch.delenv(key)


def test_defaults_match_the_table() -> None:
    s = Settings()
    assert s.data_dir == Path.home() / ".twyf"
    assert s.host == "127.0.0.1"
    assert s.port == 8321
    assert s.static_dir is None
    assert s.cors_origins == ["http://localhost:5173"]
    assert s.runtime == "queue"
    assert s.command == ["claude", "-p", "--output-format", "json"]
    assert s.max_verify_rounds == 3
    assert s.max_discussion_steps == 6
    assert s.max_turn_retries == 2
    assert s.turn_timeout_s == 300
    assert s.max_upload_mb == 1024
    assert s.parser == "auto"
    assert s.embedder == "fastembed"
    assert s.embed_model == "BAAI/bge-small-en-v1.5"
    assert s.retrieval_mode == "hybrid"
    assert s.passages_per_turn == 8
    assert s.searches_per_turn == 3
    assert s.first_read is True
    assert s.first_read_chunks == 12


def test_agents_dir_is_nearest_above_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".agents").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert Settings().agents_dir == (tmp_path / ".agents").resolve()


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TWYF_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TWYF_PORT", "9000")
    monkeypatch.setenv("TWYF_RUNTIME", "fake")
    monkeypatch.setenv("TWYF_FIRST_READ", "false")
    monkeypatch.setenv("TWYF_COMMAND", '["my-cli", "--json"]')
    s = Settings()
    assert s.data_dir == tmp_path / "data"
    assert s.port == 9000
    assert s.runtime == "fake"
    assert s.first_read is False
    assert s.command == ["my-cli", "--json"]


def test_behaviour_json_is_sorted_and_non_secret() -> None:
    data = json.loads(Settings().behaviour_json())
    assert list(data) == sorted(data)
    assert set(data) == {
        "runtime",
        "max_verify_rounds",
        "max_discussion_steps",
        "max_turn_retries",
        "turn_timeout_s",
        "parser",
        "embedder",
        "retrieval_mode",
        "first_read",
    }
    assert Settings(max_verify_rounds=5).behaviour_json() != Settings().behaviour_json()

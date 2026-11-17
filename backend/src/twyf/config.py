import json
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _nearest_agents_dir() -> Path:
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        candidate = folder / ".agents"
        if candidate.is_dir():
            return candidate
    return here / ".agents"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TWYF_", env_file=".env")

    data_dir: Path = Field(default_factory=lambda: Path.home() / ".twyf")
    agents_dir: Path = Field(default_factory=_nearest_agents_dir)
    host: str = "127.0.0.1"
    port: int = 8321
    static_dir: Path | None = None
    cors_origins: list[str] = ["http://localhost:5173"]
    runtime: Literal["fake", "queue", "command"] = "queue"
    command: list[str] = ["claude", "-p", "--output-format", "json"]
    max_verify_rounds: int = 2
    max_discussion_steps: int = 6
    max_turn_retries: int = 2
    turn_timeout_s: int = 300
    max_upload_mb: int = 1024
    parser: Literal["auto", "basic", "docling"] = "auto"
    embedder: Literal["fastembed", "hash", "none"] = "fastembed"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    retrieval_mode: Literal["keyword", "vector", "hybrid"] = "hybrid"
    passages_per_turn: int = 8
    searches_per_turn: int = 3
    first_read: bool = True
    first_read_chunks: int = 12

    def behaviour_json(self) -> str:
        """Sorted JSON of the non-secret settings that shape behaviour, snapshotted into config_versions."""
        values = {
            "runtime": self.runtime,
            "max_verify_rounds": self.max_verify_rounds,
            "max_discussion_steps": self.max_discussion_steps,
            "max_turn_retries": self.max_turn_retries,
            "turn_timeout_s": self.turn_timeout_s,
            "parser": self.parser,
            "embedder": self.embedder,
            "retrieval_mode": self.retrieval_mode,
            "first_read": self.first_read,
        }
        return json.dumps(values, sort_keys=True, separators=(",", ":"))

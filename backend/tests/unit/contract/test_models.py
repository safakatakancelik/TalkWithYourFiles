import json
from pathlib import Path
from typing import Any

import pytest

from twyf.contract import models
from twyf.contract.base import Wire
from twyf.contract.models import Citation, FileItem, MapLink, dump

SAMPLES: dict[str, dict[str, Any]] = json.loads((Path(__file__).parents[2] / "fixtures" / "samples.json").read_text())[
    "models"
]


def _model(name: str) -> type[Wire]:
    cls = getattr(models, name)
    assert issubclass(cls, Wire)
    return cls


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_models_roundtrip(name: str) -> None:
    cls = _model(name)
    obj = cls.model_validate(SAMPLES[name])
    data = dump(obj)
    assert data == SAMPLES[name]
    assert all("_" not in key for key in data)
    assert cls.model_validate(data) == obj


def test_every_wire_model_has_a_sample() -> None:
    names = {
        n
        for n, v in vars(models).items()
        if isinstance(v, type) and issubclass(v, Wire) and v.__module__ == models.__name__
    }
    assert names - {"ErrorInfo"} == set(SAMPLES)


def test_optional_fields_omitted() -> None:
    item = FileItem(id="f_1", name="a.txt", type="txt", size_kb=1, uploaded_at="2026-11-15T10:00:00.000Z")
    assert dump(item) == {
        "id": "f_1",
        "name": "a.txt",
        "type": "txt",
        "sizeKb": 1,
        "uploadedAt": "2026-11-15T10:00:00.000Z",
    }
    schema = json.dumps(Citation.model_json_schema(mode="serialization", by_alias=True))
    assert '"null"' not in schema
    required = Citation.model_json_schema(mode="serialization", by_alias=True)["required"]
    assert set(required) == {"n", "fileId", "agentId", "location", "passage", "quote"}


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValueError):
        models.Workspace.model_validate({"id": "ws_1", "name": "x", "other": 1})


def test_map_link_uses_from() -> None:
    link = MapLink.model_validate({"from": "a", "to": "b"})
    assert link.from_ == "a"
    assert dump(link) == {"from": "a", "to": "b"}

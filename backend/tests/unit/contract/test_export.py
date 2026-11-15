import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from twyf.contract.export import SCHEMA_PATH, build_schema, write_schema

SAMPLES: dict[str, dict[str, Any]] = json.loads((Path(__file__).parents[2] / "fixtures" / "samples.json").read_text())


def _committed() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def test_schema_is_current() -> None:
    assert build_schema() == _committed()


def test_write_schema_format(tmp_path: Path) -> None:
    out = tmp_path / "schema.json"
    write_schema(out)
    text = out.read_text()
    assert text.endswith("}\n")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def _validator(defs: dict[str, Any], name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": defs})


@pytest.mark.parametrize("name", sorted(SAMPLES["models"]))
def test_samples_validate(name: str) -> None:
    defs = _committed()["$defs"]
    _validator(defs, name).validate(SAMPLES["models"][name])


@pytest.mark.parametrize("name", sorted(SAMPLES["events"]))
def test_event_samples_validate(name: str) -> None:
    defs = _committed()["$defs"]
    _validator(defs, "AgentEvent").validate(SAMPLES["events"][name])


def test_schema_rejects_null_optional_and_unknown_event() -> None:
    defs = _committed()["$defs"]
    assert not _validator(defs, "FileItem").is_valid({**SAMPLES["models"]["FileItem"], "status": None})
    assert not _validator(defs, "AgentEvent").is_valid({"type": "shout"})


def test_operations_listed() -> None:
    ops = _committed()["operations"]
    assert len(ops) == 32
    upload = next(op for op in ops if op["name"] == "upload_file")
    assert upload == {
        "name": "upload_file",
        "method": "POST",
        "path": "/workspaces/{ws}/files",
        "input": {"$ref": "#/$defs/UploadFileInput"},
        "output": {"$ref": "#/$defs/FileItem"},
        "kind": "upload",
        "backendMethod": "uploadFile",
    }

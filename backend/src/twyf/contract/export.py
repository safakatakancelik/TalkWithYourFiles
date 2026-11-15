"""Writes contract/schema.json: the JSON Schema of every wire type, event and operation input, and the operations."""

import inspect
import json
import types
import typing
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import JsonSchemaMode, models_json_schema

from twyf.contract import events, models, operations, turns
from twyf.contract.base import Wire
from twyf.contract.events import AgentEvent
from twyf.contract.operations import OPERATIONS

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "contract" / "schema.json"
REF = "#/$defs/{model}"


def _wire_models(module: types.ModuleType) -> list[type[Wire]]:
    found: list[type[Wire]] = []
    for _, value in inspect.getmembers(module, inspect.isclass):
        if issubclass(value, Wire) and value.__module__ == module.__name__ and value is not events.Event:
            found.append(value)
    return found


def _ref(model: type[BaseModel]) -> dict[str, str]:
    return {"$ref": REF.format(model=model.__name__)}


def _output_schema(output: Any) -> dict[str, Any]:
    if output is None:
        return {"type": "null"}
    if output is AgentEvent:
        return {"$ref": REF.format(model="AgentEvent")}
    origin = typing.get_origin(output)
    if origin is list:
        return {"type": "array", "items": _output_schema(typing.get_args(output)[0])}
    if origin in (typing.Union, types.UnionType):
        return {"anyOf": [_output_schema(None if arg is type(None) else arg) for arg in typing.get_args(output)]}
    return _ref(output)


def _inline_opt(node: Any, aliases: dict[str, Any]) -> Any:
    """Replace each reference to an `Opt[...]` alias by its content, and drop the `default: null` beside it."""
    if isinstance(node, list):
        return [_inline_opt(item, aliases) for item in typing.cast(list[Any], node)]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in typing.cast(dict[str, Any], node).items():
        out[key] = _inline_opt(value, aliases)
    ref = out.get("$ref")
    if isinstance(ref, str) and ref.removeprefix("#/$defs/") in aliases:
        del out["$ref"]
        out = {**_inline_opt(aliases[ref.removeprefix("#/$defs/")], aliases), **out}
        if out.get("default", ...) is None:
            del out["default"]
    return out


def build_schema() -> dict[str, Any]:
    wire = _wire_models(models) + _wire_models(events) + _wire_models(operations)
    wire += [turns.TurnOffer, turns.Usage]
    pairs: list[tuple[type[BaseModel], JsonSchemaMode]] = [(m, "serialization") for m in wire]
    _, top = models_json_schema(pairs, by_alias=True, ref_template=REF)
    defs: dict[str, Any] = dict(top.get("$defs", {}))
    union = TypeAdapter(AgentEvent).json_schema(mode="serialization", by_alias=True, ref_template=REF)
    defs.update(union.pop("$defs", {}))
    defs["AgentEvent"] = {"title": "AgentEvent", **union}
    aliases = {name: defs.pop(name) for name in [n for n in defs if n.startswith("Opt_")]}
    defs = _inline_opt(defs, aliases)
    ops: list[dict[str, Any]] = []
    for op in OPERATIONS:
        assert op.input is not None
        ops.append(
            {
                "name": op.name,
                "method": op.method,
                "path": op.path,
                "input": _ref(op.input),
                "output": _output_schema(op.output),
                "kind": op.kind,
                "backendMethod": op.backend_method,
            }
        )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "twyf contract",
        "$defs": defs,
        "operations": ops,
    }


def write_schema(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_schema(), indent=2, sort_keys=True) + "\n")

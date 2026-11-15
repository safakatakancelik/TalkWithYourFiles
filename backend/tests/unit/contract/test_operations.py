import inspect
import re

from twyf.contract.base import Wire
from twyf.contract.operations import OPERATIONS, get_operation, resolve_handler
from twyf.recording.context import RequestContext
from twyf.services.errors import HTTP_STATUS, ServiceError


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def test_operations_unique_and_resolvable() -> None:
    assert len(OPERATIONS) == 32
    names = [op.name for op in OPERATIONS]
    assert len(set(names)) == len(names)
    routes = [(op.method, op.path) for op in OPERATIONS]
    assert len(set(routes)) == len(routes)
    for op in OPERATIONS:
        handler = resolve_handler(op)
        assert callable(handler)
        params = list(inspect.signature(handler).parameters.values())
        assert [p.name for p in params[:2]] == ["ctx", "input"]
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params[2:]), op.name
        assert op.input is not None and issubclass(op.input, Wire)
        assert op.input.__name__ == _camel(op.name) + "Input"
        assert get_operation(op.name) is op


def test_path_fields_are_input_fields() -> None:
    for op in OPERATIONS:
        assert op.input is not None
        for field in re.findall(r"{(\w+)}", op.path):
            assert field in op.input.model_fields, (op.name, field)


def test_error_codes_have_http_statuses() -> None:
    assert HTTP_STATUS == {"validation": 400, "not_found": 404, "conflict": 409, "too_large": 413, "internal": 500}
    error = ServiceError("conflict", "busy", {"id": 1})
    assert (error.code, error.message, error.details, str(error)) == ("conflict", "busy", {"id": 1}, "conflict: busy")


def test_request_context_helpers() -> None:
    ctx = RequestContext(actor_id="u_local", source="api", user_id="u_local", request_id="r1")
    assert ctx.caused_by(5).cause_event_id == 5
    agent = ctx.as_actor("a_1")
    assert (agent.actor_id, agent.source, agent.request_id) == ("a_1", "internal", "r1")

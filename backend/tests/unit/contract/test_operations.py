import inspect
import re

import pytest

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


def test_stubs_raise_not_implemented() -> None:
    ctx = RequestContext(actor_id="u_local", source="api", user_id="u_local", request_id="test")
    op = get_operation("fail_turn")
    assert op.input is not None
    with pytest.raises(ServiceError) as raised:
        resolve_handler(op)(ctx, op.input.model_validate({"turnId": "t_1", "leaseToken": "x", "reason": "r"}))
    assert raised.value.code == "internal"
    assert HTTP_STATUS[raised.value.code] == 500


def test_request_context_helpers() -> None:
    ctx = RequestContext(actor_id="u_local", source="api", user_id="u_local", request_id="r1")
    assert ctx.caused_by(5).cause_event_id == 5
    agent = ctx.as_actor("a_1")
    assert (agent.actor_id, agent.source, agent.request_id) == ("a_1", "internal", "r1")

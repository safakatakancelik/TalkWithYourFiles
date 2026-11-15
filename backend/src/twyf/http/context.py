from fastapi import Request

from twyf.ids import new_id
from twyf.recording.context import RequestContext

LOCAL_USER = "u_local"
SOURCES = {"ui", "mcp"}


def request_id(request: Request) -> str:
    rid: str | None = getattr(request.state, "request_id", None)
    if rid is None:
        rid = request.headers.get("x-request-id") or new_id("req")
        request.state.request_id = rid
    return rid


def context_from_request(request: Request) -> RequestContext:
    """The door is named by X-TWYF-Source: `ui` or `mcp`, anything else is `api`. It is a record, not a control."""
    source = request.headers.get("x-twyf-source", "").strip().lower()
    return RequestContext(
        actor_id=LOCAL_USER,
        source=source if source in SOURCES else "api",
        user_id=LOCAL_USER,
        request_id=request_id(request),
        client=request.headers.get("x-twyf-client"),
    )

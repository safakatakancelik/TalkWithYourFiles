from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RequestContext:
    """Who is acting, through which door, and what the action belongs to."""

    actor_id: str
    source: str
    user_id: str
    request_id: str
    client: str | None = None
    cause_event_id: int | None = None

    def caused_by(self, event_id: int) -> "RequestContext":
        return replace(self, cause_event_id=event_id)

    def as_actor(self, actor_id: str, source: str = "internal") -> "RequestContext":
        return replace(self, actor_id=actor_id, source=source)

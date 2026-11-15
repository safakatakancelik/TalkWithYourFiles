# Local stub: simpleeval ships no type information. Only what twyf uses.
from collections.abc import Callable
from typing import Any

class InvalidExpression(Exception): ...

class SimpleEval:
    operators: dict[type, Callable[..., Any]]
    def __init__(
        self,
        operators: dict[type, Callable[..., Any]] | None = ...,
        functions: dict[str, Callable[..., Any]] | None = ...,
        names: dict[str, Any] | None = ...,
    ) -> None: ...
    def eval(self, expr: str) -> Any: ...

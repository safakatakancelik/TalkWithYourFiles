"""The HTTP door. One route per operation in OPERATIONS, generated here. No rules live in this module."""

import inspect
import logging
import re
import typing
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, File, Path, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError, create_model
from pydantic.alias_generators import to_camel

from twyf import __version__
from twyf.agents.definitions import sync, sync_config
from twyf.config import Settings
from twyf.contract.base import Wire
from twyf.contract.operations import OPERATIONS, CreateWorkspaceInput, Operation, resolve_handler
from twyf.db.connection import transaction
from twyf.db.migrate import migrate
from twyf.db.repos import embeddings
from twyf.db.repos import workspaces as workspaces_repo
from twyf.files.ingest import ingest, pending_ingestion
from twyf.files.jobs import Jobs, ThreadJobs
from twyf.http import errors
from twyf.http.context import LOCAL_USER, context_from_request, request_id
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.retrieval.embedder import get_embedder
from twyf.retrieval.reembed import reembed
from twyf.services import state, workspaces
from twyf.services.errors import ServiceError

log = logging.getLogger(__name__)

API = "/api/v1"
FIRST_WORKSPACE = "My workspace"
"""Placeholder for the runtime boundary (task B21 onward)."""
type AgentRuntime = Any

_KW = inspect.Parameter.KEYWORD_ONLY


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, list):
        return [_dump(v) for v in typing.cast(list[Any], value)]
    return value


def _query_annotation(annotation: Any, default: Any) -> Any:
    """`Opt[int]` becomes `int | None` for FastAPI, which does not read the alias."""
    args = typing.get_args(annotation)
    if default is None and args:
        return args[0] | None
    return annotation


def _body_model(op: Operation, fields: list[str]) -> type[Wire]:
    assert op.input is not None
    definitions: dict[str, Any] = {
        name: (op.input.model_fields[name].annotation, op.input.model_fields[name]) for name in fields
    }
    return create_model(op.input.__name__.removesuffix("Input") + "Body", __base__=Wire, **definitions)


def _endpoint(op: Operation) -> Callable[..., Awaitable[Response]]:
    """An endpoint with a real signature, so FastAPI documents and parses path, query, body and file."""
    assert op.input is not None
    input_model = op.input
    path_fields = re.findall(r"{(\w+)}", op.path)
    other = [name for name in input_model.model_fields if name not in path_fields]
    params = [inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request)]
    params += [inspect.Parameter(name, _KW, default=Path(), annotation=str) for name in path_fields]
    query: list[str] = []
    body: type[Wire] | None = None
    if op.kind == "upload":
        params.append(inspect.Parameter("file", _KW, default=File(), annotation=UploadFile))
    elif op.method == "GET":
        for name in other:
            field = input_model.model_fields[name]
            params.append(
                inspect.Parameter(
                    name, _KW, default=Query(field.default, alias=to_camel(name)),
                    annotation=_query_annotation(field.annotation, field.default),
                )
            )  # fmt: skip
            query.append(name)
    elif other:
        body = _body_model(op, other)
        params.append(inspect.Parameter("body", _KW, default=Body(), annotation=body))

    async def endpoint(request: Request, **kwargs: Any) -> Response:
        ctx = context_from_request(request)
        values: dict[str, Any] = {name: kwargs[name] for name in path_fields}
        values |= {name: kwargs[name] for name in query if kwargs[name] is not None}
        if body is not None:
            values |= typing.cast(BaseModel, kwargs["body"]).model_dump(exclude_unset=True)
        try:
            data = input_model.model_validate(values)
            if op.kind == "stream":
                raise ServiceError("internal", "not implemented")
            handler = resolve_handler(op)
            if op.kind == "upload":
                upload = typing.cast(UploadFile, kwargs["file"])
                result = await run_in_threadpool(handler, ctx, data, name=upload.filename or "", stream=upload.file)
            elif inspect.iscoroutinefunction(handler):
                result = await handler(ctx, data)
            else:
                result = await run_in_threadpool(handler, ctx, data)
        except ServiceError as error:
            return errors.from_service_error(error)
        except ValidationError as error:
            return errors.from_validation_error(error)
        except Exception as error:  # noqa: BLE001 -- every failure becomes an ErrorBody
            return errors.internal(error)
        if op.output is None:
            return Response(status_code=204)
        return JSONResponse(_dump(result))

    endpoint.__signature__ = inspect.Signature(params)  # pyright: ignore[reportFunctionMemberAccess] -- FastAPI reads it
    endpoint.__name__ = op.name
    return endpoint


def _startup(settings: Settings, jobs: Jobs) -> None:
    """Migrate, snapshot definitions and config, make the first workspace, and resume background work."""
    migrate(settings.data_dir / "twyf.db")
    system = RequestContext(actor_id="system", source="internal", user_id=LOCAL_USER, request_id=new_id("start"))
    with state.db() as conn:
        with transaction(conn):
            sync(conn, system, settings)
            config_id = sync_config(conn, system, settings)
            record(conn, system, "server.started", payload={"version": __version__, "runtime": settings.runtime},
                   config_version_id=config_id)  # fmt: skip
        if not workspaces_repo.list(conn, LOCAL_USER):
            workspaces.create(system, CreateWorkspaceInput(name=FIRST_WORKSPACE))
        for file_version_id in pending_ingestion(conn):
            jobs.submit(lambda fv=file_version_id: ingest(state.connect, system, settings, fv))
        embedder = get_embedder(settings)
        if embedder.dim and embeddings.find_model(conn, embedder) is None:
            jobs.submit(lambda: log.info("re-embedded %d", reembed(state.connect, system, embedder)))


def build_app(settings: Settings, runtime: AgentRuntime | None = None, jobs: Jobs | None = None) -> FastAPI:
    work: Jobs = jobs if jobs is not None else ThreadJobs()
    state.configure(settings, work)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        state.configure(settings, work)
        await run_in_threadpool(_startup, settings, work)
        yield

    app = FastAPI(title="Talk With Your Files", version=__version__, lifespan=lifespan)
    errors.install(app)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )  # fmt: skip

    @app.middleware("http")
    async def add_request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request_id(request)
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    for op in OPERATIONS:
        app.add_api_route(API + op.path, _endpoint(op), methods=[op.method], name=op.name, description=op.description)

    @app.get(API + "/health")
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction] -- registered by the decorator
        return {"status": "ok", "version": __version__, "runtime": settings.runtime}

    if settings.static_dir is not None:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    return app

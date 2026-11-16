import argparse
import sys
import typing
from pathlib import Path

COMMANDS = ["serve", "mcp", "seed-demo", "export-contract", "events", "eval"]
RuntimeName = typing.Literal["fake", "queue", "command"]
DEMO_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "demo"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="twyf", description="Talk With Your Files backend")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        command = sub.add_parser(name)
        if name == "mcp":
            command.add_argument("--http", action="store_true", help="serve Streamable HTTP on 127.0.0.1:8322/mcp")
        if name == "serve":
            command.add_argument("--runtime", choices=["fake", "queue", "command"], help="overrides TWYF_RUNTIME")
            command.add_argument("--fake-script", type=Path, help="a FakeRuntime script (JSON) for --runtime fake")
        if name == "seed-demo":
            command.add_argument("--fixtures", type=Path, default=DEMO_FIXTURES, help="the folder of demo files")
    return parser


def export_contract() -> int:
    from twyf.contract.export import SCHEMA_PATH, write_schema

    write_schema(SCHEMA_PATH)
    print(f"wrote {SCHEMA_PATH}")
    return 0


def serve(runtime: str | None, fake_script: Path | None) -> int:
    import uvicorn

    from twyf.config import Settings
    from twyf.http.app import build_app
    from twyf.runtime.fake import FakeRuntime

    settings = Settings(runtime=typing.cast(RuntimeName, runtime)) if runtime else Settings()
    agents = FakeRuntime.from_file(fake_script) if fake_script is not None else None
    uvicorn.run(build_app(settings, runtime=agents), host=settings.host, port=settings.port)
    return 0


def seed_demo(fixtures: Path) -> int:
    from twyf.agents.definitions import sync, sync_config
    from twyf.config import Settings
    from twyf.db.connection import transaction
    from twyf.db.migrate import migrate
    from twyf.files.jobs import InlineJobs
    from twyf.ids import new_id
    from twyf.recording.context import RequestContext
    from twyf.services import demo, state
    from twyf.services.errors import ServiceError

    settings = Settings()
    migrate(settings.data_dir / "twyf.db")
    state.configure(settings, InlineJobs())
    ctx = RequestContext(actor_id="system", source="cli", user_id="u_local", request_id=new_id("cli"))
    with state.db() as conn, transaction(conn):
        sync(conn, ctx.as_actor("system"), settings)
        sync_config(conn, ctx.as_actor("system"), settings)
    try:
        demo.seed(ctx, settings, fixtures)
    except ServiceError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    print(f"seeded the demo workspace in {settings.data_dir}")
    return 0


def mcp(http_transport: bool) -> int:
    import os

    import httpx

    from twyf.mcp.server import build_server

    api_url = os.environ.get("TWYF_API_URL", "http://127.0.0.1:8321").rstrip("/")
    server = build_server(httpx.AsyncClient(base_url=api_url + "/api/v1", timeout=None))
    if http_transport:
        server.run(
            transport="streamable-http", host="127.0.0.1", port=8322, streamable_http_path="/mcp", stateless_http=True
        )
    else:
        server.run(transport="stdio")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "export-contract":
        return export_contract()
    if args.command == "serve":
        return serve(args.runtime, args.fake_script)
    if args.command == "seed-demo":
        return seed_demo(args.fixtures)
    if args.command == "mcp":
        return mcp(bool(args.http))
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

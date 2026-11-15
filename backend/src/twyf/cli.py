import argparse
import sys

COMMANDS = ["serve", "mcp", "seed-demo", "export-contract", "events", "eval"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="twyf", description="Talk With Your Files backend")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        command = sub.add_parser(name)
        if name == "mcp":
            command.add_argument("--http", action="store_true", help="serve Streamable HTTP on 127.0.0.1:8322/mcp")
    return parser


def export_contract() -> int:
    from twyf.contract.export import SCHEMA_PATH, write_schema

    write_schema(SCHEMA_PATH)
    print(f"wrote {SCHEMA_PATH}")
    return 0


def serve() -> int:
    import uvicorn

    from twyf.config import Settings
    from twyf.http.app import build_app

    settings = Settings()
    uvicorn.run(build_app(settings), host=settings.host, port=settings.port)
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
        return serve()
    if args.command == "mcp":
        return mcp(bool(args.http))
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

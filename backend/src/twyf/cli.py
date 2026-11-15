import argparse
import sys

COMMANDS = ["serve", "mcp", "seed-demo", "export-contract", "events", "eval"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="twyf", description="Talk With Your Files backend")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        sub.add_parser(name)
    return parser


def export_contract() -> int:
    from twyf.contract.export import SCHEMA_PATH, write_schema

    write_schema(SCHEMA_PATH)
    print(f"wrote {SCHEMA_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "export-contract":
        return export_contract()
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

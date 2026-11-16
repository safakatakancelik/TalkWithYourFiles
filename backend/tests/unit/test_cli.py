import argparse
import io
import json
import logging

import pytest

from tests.conftest import EventsHelper
from twyf import cli, logging_setup
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.contract.operations import CreateWorkspaceInput
from twyf.logging_setup import setup_logging
from twyf.recording.context import RequestContext
from twyf.services import workspaces


def test_log_lines_are_json_with_request_id(settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(settings)
    token = logging_setup.request_id.set("req-42")
    q = logging_setup.question_id.set("q_1")
    try:
        logging.getLogger("twyf.test").info("hello %s", "there")
    finally:
        logging_setup.request_id.reset(token)
        logging_setup.question_id.reset(q)
    line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert (line["message"], line["request_id"], line["question_id"], line["level"]) == (
        "hello there",
        "req-42",
        "q_1",
        "info",
    )
    assert "turn_id" not in line
    written = (settings.data_dir / "logs" / "twyf.log").read_text().strip().splitlines()
    assert json.loads(written[-1])["request_id"] == "req-42"
    for handler in [h for h in logging.getLogger().handlers if getattr(h, "twyf", False)]:
        logging.getLogger().removeHandler(handler)


def test_events_command_prints_filtered_rows(
    ws: Workspace, ctx: RequestContext, settings: Settings, events: EventsHelper, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = workspaces.create(ctx, CreateWorkspaceInput(name="Other"))
    monkeypatch.setenv("TWYF_DATA_DIR", str(settings.data_dir))
    out = io.StringIO()
    args = argparse.Namespace(workspace=ws.id, question=None, type="workspace.created", after=0, tail=False)
    assert cli.events(args, out) == 0
    lines = out.getvalue().strip().splitlines()
    assert len(lines) == 1 and "workspace.created" in lines[0] and ws.id in lines[0] and other.id not in lines[0]
    out = io.StringIO()
    first = events()[0].id
    cli.events(argparse.Namespace(workspace=None, question=None, type=None, after=first, tail=False), out)
    printed = [int(line.split()[0]) for line in out.getvalue().strip().splitlines()]
    assert printed == [e.id for e in events() if e.id > first]


def test_cli_parses_every_command() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["mcp", "--http"]).http is True
    assert parser.parse_args(["serve", "--runtime", "fake"]).runtime == "fake"
    assert parser.parse_args(["events", "--tail", "--type", "x"]).tail is True
    assert parser.parse_args(["eval", "--case", "demo", "--case", "lease end"]).case == ["demo", "lease end"]

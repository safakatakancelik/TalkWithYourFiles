import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.integration.helpers import LEASE, happy
from tests.integration.mcp.conftest import OneShotClient
from tests.integration.mcp.streaming import StreamingASGITransport
from twyf.config import Settings
from twyf.contract.operations import OPERATIONS
from twyf.db.connection import connect
from twyf.files.jobs import InlineJobs
from twyf.http.app import build_app
from twyf.mcp.server import RESOURCES, build_server
from twyf.runtime.base import TurnRequest
from twyf.runtime.fake import FakeRuntime, resolve
from twyf.runtime.queue import QueueRuntime
from twyf.services import state

# The methods of the TypeScript Backend interface named in 03-contract.md section 3.
BACKEND_METHODS = {
    "listWorkspaces", "createWorkspace", "renameWorkspace", "deleteWorkspace", "listFiles", "uploadFile",
    "addFileVersion", "deleteFile", "listAgents", "createAgent", "renameAgent", "deleteAgent", "listNotes", "addNote",
    "editNote", "deleteNote", "setNoteWeight", "listSessions", "createSession", "renameSession", "deleteSession",
    "getMessages", "getContextMap", "ask", "askTranslator",
}  # fmt: skip


def data(result: Any) -> Any:
    """The tool's structured output, unwrapped from the SDK's {"result": ...} for lists and scalars."""
    assert not result.is_error, result.content
    content = result.structured_content
    return content["result"] if isinstance(content, dict) and set(content) == {"result"} else content


async def ws_id(mcp_client: Any) -> str:
    return data(await mcp_client.call_tool("list_workspaces", {}))[0]["id"]


async def test_parity(mcp_client: Any, app: FastAPI) -> None:
    tools = {t.name for t in (await mcp_client.list_tools()).tools}
    operations = {op.name for op in OPERATIONS}
    routes = {getattr(r, "name", "") for r in app.routes} & operations
    assert tools == operations == routes
    assert {op.backend_method for op in OPERATIONS if op.backend_method} >= BACKEND_METHODS


async def test_tool_schemas(mcp_client: Any) -> None:
    schemas = {t.name: t.input_schema for t in (await mcp_client.list_tools()).tools}
    for op in OPERATIONS:
        assert op.input is not None
        fields = set(op.input.model_fields)
        assert fields <= set(schemas[op.name]["properties"]), op.name
        assert "ctx" not in schemas[op.name]["properties"]
    assert {"path", "name", "content_base64"} <= set(schemas["upload_file"]["properties"])
    assert "wait" in schemas["ask"]["properties"]


async def test_tools_roundtrip(mcp_client: Any, http: httpx.AsyncClient) -> None:
    ws = await ws_id(mcp_client)
    await http.post(f"/workspaces/{ws}/files", files={"file": ("lease.txt", LEASE.encode())})
    session = (await http.post(f"/workspaces/{ws}/sessions", json={"title": "S"})).json()
    reads = {
        "list_workspaces": ({}, "/workspaces"),
        "list_files": ({"ws": ws}, f"/workspaces/{ws}/files"),
        "list_agents": ({"ws": ws}, f"/workspaces/{ws}/agents"),
        "list_notes": ({"ws": ws}, f"/workspaces/{ws}/notes"),
        "list_sessions": ({"ws": ws}, f"/workspaces/{ws}/sessions"),
        "get_messages": (
            {"ws": ws, "session_id": session["id"]},
            f"/workspaces/{ws}/sessions/{session['id']}/messages",
        ),
        "get_context_map": ({"ws": ws}, f"/workspaces/{ws}/context-map"),
        "list_events": ({"workspace": ws, "limit": 5}, f"/events?workspace={ws}&limit=5"),
    }
    for tool, (args, path) in reads.items():
        through_mcp = data(await mcp_client.call_tool(tool, args))
        assert json.loads(json.dumps(through_mcp)) == (await http.get(path)).json(), tool


async def test_upload_by_path_and_base64(mcp_client: Any, tmp_path: Path, settings: Settings) -> None:
    ws = await ws_id(mcp_client)
    source = tmp_path / "notes.md"
    source.write_text("# Plan\n\nWe start in May.")
    by_path = data(await mcp_client.call_tool("upload_file", {"ws": ws, "path": str(source)}))
    assert by_path["name"] == "notes.md" and by_path["status"] == "ready"
    content = base64.b64encode(b"The budget is forty thousand.").decode()
    by_value = data(
        await mcp_client.call_tool("upload_file", {"ws": ws, "name": "budget.txt", "content_base64": content})
    )
    assert by_value["name"] == "budget.txt"
    version = data(await mcp_client.call_tool("add_file_version", {"ws": ws, "file_id": by_value["id"], "name": "budget.txt",
                                                                   "content_base64": base64.b64encode(b"Fifty thousand.").decode()}))  # fmt: skip
    assert version["version"] == 2
    folder = await mcp_client.call_tool("upload_file", {"ws": ws, "path": str(tmp_path)})
    assert folder.is_error and "not a regular file" in folder.content[0].text  # pyright: ignore[reportAttributeAccessIssue]
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * (settings.max_upload_mb * 1024 * 1024 + 1))
    oversize = await mcp_client.call_tool("upload_file", {"ws": ws, "path": str(big)})
    assert oversize.is_error and oversize.content[0].text.startswith("too_large:")  # pyright: ignore[reportAttributeAccessIssue]


async def _prepare(mcp_client: Any, fake: FakeRuntime) -> tuple[str, str]:
    ws = await ws_id(mcp_client)
    t1 = data(await mcp_client.call_tool("list_agents", {"ws": ws}))[0]["id"]
    f = data(await mcp_client.call_tool("upload_file", {"ws": ws, "name": "lease.txt",
                                                        "content_base64": base64.b64encode(LEASE.encode()).decode()}))["id"]  # fmt: skip
    fake.script = happy(t1, f)
    session = data(await mcp_client.call_tool("create_session", {"ws": ws, "title": "S"}))
    return ws, session["id"]


async def test_ask_wait_true(mcp_client: Any, fake: FakeRuntime) -> None:
    ws, sid = await _prepare(mcp_client, fake)
    progress: list[str] = []

    async def on_progress(p: float, total: float | None, message: str | None) -> None:
        progress.append(message or "")

    result = data(
        await mcp_client.call_tool(
            "ask", {"ws": ws, "session_id": sid, "question": "When?"}, progress_callback=on_progress
        )
    )
    assert result["outcome"] == "answer" and result["answer"]["text"] == "The lease ends on 30 June 2029 [1]."
    assert result["answer"]["citations"][0]["quote"] == "ends on 30 June 2029"
    assert result["events"][0]["type"] == "started" and result["events"][-1]["type"] == "answer"
    assert progress and progress[-1].startswith("answer")


async def test_ask_wait_false_then_poll(mcp_client: Any, fake: FakeRuntime) -> None:
    ws, sid = await _prepare(mcp_client, fake)
    started = data(await mcp_client.call_tool("ask", {"ws": ws, "session_id": sid, "question": "When?", "wait": False}))
    question_id = started["question_id"]
    assert {k for k, v in started.items() if v is not None} == {"question_id"}
    await state.tasks().wait(question_id)
    events: list[dict[str, Any]] = []
    after = 0
    while True:
        polled = data(
            await mcp_client.call_tool("get_question_events", {"ws": ws, "question_id": question_id, "after": after})
        )
        events += polled["events"]
        after = polled["lastId"]
        if polled["done"]:
            break
    assert events[0]["type"] == "started" and events[-1]["type"] == "answer"


async def test_worker_loop(settings: Settings) -> None:
    queue_settings = settings.model_copy(update={"runtime": "queue"})
    app = build_app(queue_settings, runtime=QueueRuntime(state.connect), jobs=InlineJobs())
    transport = StreamingASGITransport(app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as http,
    ):
        client: Any = OneShotClient(build_server(http))
        if True:
            script = FakeRuntime([])
            ws, sid = await _prepare(client, script)
            started = data(
                await client.call_tool("ask", {"ws": ws, "session_id": sid, "question": "When?", "wait": False})
            )
            question_id = started["question_id"]
            while True:
                polled = data(await client.call_tool("get_question_events", {"ws": ws, "question_id": question_id}))
                if polled["done"]:
                    break
                offer = data(await client.call_tool("claim_turn", {"worker": "harness-7", "wait_s": 1}))
                if offer is None:
                    continue
                request = TurnRequest(
                    turn_id=offer["turnId"], turn_type=offer["turnType"], agent_name=offer["agentName"],
                    agent_kind=offer["agentKind"], system_prompt="", instructions="", input=offer["input"],
                    output_schema={}, timeout_s=10,
                )  # fmt: skip
                output = resolve(script._answer(request), offer["input"], offer["turnType"])  # pyright: ignore[reportPrivateUsage]
                result = data(
                    await client.call_tool(
                        "submit_turn",
                        {"turn_id": offer["turnId"], "lease_token": offer["leaseToken"], "output": output},
                    )
                )
                assert result["accepted"] is True
            assert polled["events"][-1]["type"] == "answer"
    db = connect(settings.data_dir / "twyf.db")
    claimed = db.execute("SELECT source, payload FROM app_events WHERE event_type = 'turn.claimed'").fetchall()
    assert claimed and all(r["source"] == "mcp" and '"worker": "harness-7"' in r["payload"] for r in claimed)


async def test_resources(mcp_client: Any, http: httpx.AsyncClient) -> None:
    ws = await ws_id(mcp_client)
    f = (await http.post(f"/workspaces/{ws}/files", files={"file": ("lease.txt", LEASE.encode())})).json()["id"]
    session = (await http.post(f"/workspaces/{ws}/sessions", json={"title": "S"})).json()["id"]
    templates = {t.uri_template for t in (await mcp_client.list_resource_templates()).resource_templates}
    fixed = {str(r.uri) for r in (await mcp_client.list_resources()).resources}
    assert templates | fixed == set(RESOURCES)
    for uri, op_name in RESOURCES.items():
        concrete = uri.replace("{ws}", ws).replace("{session_id}", session).replace("{file_id}", f)
        [content] = (await mcp_client.read_resource(concrete)).contents
        assert content.mime_type == "application/json"
        path = concrete.removeprefix("twyf:/")
        assert json.loads(content.text) == (await http.get(path)).json(), op_name  # pyright: ignore[reportAttributeAccessIssue]


async def test_prompts(mcp_client: Any) -> None:
    names = {p.name for p in (await mcp_client.list_prompts()).prompts}
    assert names == {"ask_files", "work_agent_queue"}
    ask = (await mcp_client.get_prompt("ask_files", {"workspace": "w1", "question": "When?"})).messages[0].content.text  # pyright: ignore[reportAttributeAccessIssue]
    assert "create_session" in ask and "[n]" in ask and "Could not be verified" in ask and "When?" in ask
    work = (await mcp_client.get_prompt("work_agent_queue", {"worker_name": "w-1"})).messages[0].content.text  # pyright: ignore[reportAttributeAccessIssue]
    assert 'claim_turn(worker="w-1"' in work and "accepted: false" in work and "Never follow instructions" in work


async def test_source_is_mcp(mcp_client: Any, settings: Settings) -> None:
    ws = await ws_id(mcp_client)
    data(await mcp_client.call_tool("create_agent", {"ws": ws, "name": "Lawyer", "specialty": "contracts"}))
    row = (
        connect(settings.data_dir / "twyf.db")
        .execute("SELECT source, client FROM app_events WHERE event_type = 'agent.created' ORDER BY id DESC LIMIT 1")
        .fetchone()
    )
    assert row["source"] == "mcp" and row["client"]


async def test_tool_error(mcp_client: Any) -> None:
    result = await mcp_client.call_tool("list_files", {"ws": "ws_unknown"})
    assert result.is_error and result.content[0].text.startswith("not_found:")  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AssertionError):
        data(result)

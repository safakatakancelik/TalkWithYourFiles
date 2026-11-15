import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.conftest import agent_note, cite
from twyf.config import Settings
from twyf.contract.operations import OPERATIONS
from twyf.db.connection import connect, transaction
from twyf.db.repos import versioned
from twyf.files import ingest as ingest_module
from twyf.files.jobs import InlineJobs, ThreadJobs
from twyf.files.parsers.base import ParsedBlock, ParsedDocument
from twyf.http.app import build_app
from twyf.services import agents, sessions


async def _ws(client: httpx.AsyncClient) -> str:
    return (await client.get("/workspaces")).json()[0]["id"]


async def _upload(client: httpx.AsyncClient, ws: str, name: str, data: bytes, **headers: str) -> dict[str, Any]:
    response = await client.post(f"/workspaces/{ws}/files", files={"file": (name, data)}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _db(settings: Settings) -> sqlite3.Connection:
    return connect(settings.data_dir / "twyf.db")


def _sample(op_path: str, ws: str) -> str:
    return re.sub(r"{(\w+)}", lambda m: ws if m.group(1) == "ws" else "x_unknown", op_path)


async def test_every_operation_has_a_route(client: httpx.AsyncClient) -> None:
    ws = await _ws(client)
    for op in OPERATIONS:
        response = await client.request(op.method, _sample(op.path, ws), json={} if op.method != "GET" else None)
        assert response.status_code != 405, op.name
        body = response.json() if response.content else {}
        if response.status_code == 404:
            assert body["error"]["message"] != "No such route", op.name
        if op.kind == "stream":
            assert response.status_code in (400, 404, 500), op.name


async def test_workspace_lifecycle(client: httpx.AsyncClient, settings: Settings) -> None:
    created = (await client.post("/workspaces", json={"name": "Projects"})).json()
    renamed = (await client.patch(f"/workspaces/{created['id']}", json={"name": "Renamed"})).json()
    assert renamed == {"id": created["id"], "name": "Renamed"}
    assert (await client.delete(f"/workspaces/{created['id']}")).status_code == 204
    names = [w["name"] for w in (await client.get("/workspaces")).json()]
    assert names == ["My workspace"]
    for method, path in [("GET", "/files"), ("GET", "/agents"), ("GET", "/notes"), ("GET", "/sessions"),
                         ("GET", "/context-map"), ("PATCH", ""), ("DELETE", "")]:  # fmt: skip
        response = await client.request(
            method, f"/workspaces/{created['id']}{path}", json={"name": "x"} if method == "PATCH" else None
        )
        assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
    assert _db(settings).execute("SELECT COUNT(*) FROM workspaces WHERE id = ?", (created["id"],)).fetchone()[0] == 1


async def test_upload_and_list(client: httpx.AsyncClient) -> None:
    ws = await _ws(client)
    item = await _upload(client, ws, "notes.md", b"# Plan\n\nWe start in May.")
    assert (item["name"], item["type"], item["version"]) == ("notes.md", "md", 1)
    listed = (await client.get(f"/workspaces/{ws}/files")).json()
    assert [(f["id"], f["status"]) for f in listed] == [(item["id"], "ready")]
    graph = (await client.get(f"/workspaces/{ws}/context-map")).json()
    assert {"id": item["id"], "label": "notes.md", "kind": "file"} in graph["nodes"]


async def test_upload_too_large(settings: Settings) -> None:
    app = build_app(settings.model_copy(update={"max_upload_mb": 1}), jobs=InlineJobs())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as client,
    ):
        ws = await _ws(client)
        response = await client.post(f"/workspaces/{ws}/files", files={"file": ("big.txt", b"x" * (1024 * 1024 + 1))})
        assert response.status_code == 413 and response.json()["error"]["code"] == "too_large"


async def test_upload_traversal_name(client: httpx.AsyncClient, settings: Settings) -> None:
    ws = await _ws(client)
    item = await _upload(client, ws, "../../etc/passwd.txt", b"root:x:0:0")
    assert item["name"] == "../../etc/passwd.txt"
    location = _db(settings).execute("SELECT location FROM v_files WHERE id = ?", (item["id"],)).fetchone()[0]
    assert re.fullmatch(r"files/[0-9a-f]{2}/[0-9a-f]{64}", location)
    assert not (settings.data_dir.parent / "etc").exists()


async def test_agents_and_notes(client: httpx.AsyncClient) -> None:
    ws = await _ws(client)
    created = (await client.post(f"/workspaces/{ws}/agents", json={"name": "Lawyer", "specialty": "contracts"})).json()
    assert created["name"] == "Lawyer" and created["specialty"] == "contracts"
    assert [a["name"] for a in (await client.get(f"/workspaces/{ws}/agents")).json()] == [
        "Translator 1",
        "Translator 2",
        "Lawyer",
    ]
    item = await _upload(client, ws, "a.txt", b"Some text.")
    ids = []
    for text in ("one", "two"):
        note = (await client.post(f"/workspaces/{ws}/notes", json={"fileId": item["id"], "text": text})).json()
        assert (note["kind"], note["authorId"], note["citations"], note["weight"]) == (
            "interpretation",
            "user",
            [],
            "normal",
        )
        ids.append(note["id"])
    response = await client.post(f"/workspaces/{ws}/notes/weight", json={"noteIds": ids, "weight": "high"})
    assert response.status_code == 204
    assert {n["weight"] for n in (await client.get(f"/workspaces/{ws}/notes")).json()} == {"high"}


async def test_error_shapes(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = await _ws(client)
    cases: list[tuple[int, str, httpx.Response]] = [
        (400, "validation", await client.post("/workspaces", json={"nam": "typo"})),
        (
            400,
            "validation",
            await client.post(f"/workspaces/{ws}/notes/weight", json={"noteIds": [], "weight": "huge"}),
        ),
        (404, "not_found", await client.get("/workspaces/ws_nope/files")),
    ]
    from twyf.services import workspaces as service
    from twyf.services.errors import ServiceError

    def conflict(*args: object) -> None:
        raise ServiceError("conflict", "busy")

    def crash(*args: object) -> None:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(service, "rename", conflict)
    cases.append((409, "conflict", await client.patch(f"/workspaces/{ws}", json={"name": "x"})))
    monkeypatch.setattr(service, "delete", crash)
    cases.append((500, "internal", await client.delete(f"/workspaces/{ws}")))
    for status, code, response in cases:
        assert response.status_code == status
        body = response.json()
        assert set(body) == {"error"} and body["error"]["code"] == code and body["error"]["message"]
    assert "secret" not in cases[-1][2].text


async def test_source_and_client_headers(client: httpx.AsyncClient, settings: Settings) -> None:
    await client.post("/workspaces", json={"name": "A"}, headers={"X-TWYF-Source": "ui", "X-TWYF-Client": "browser"})
    await client.post("/workspaces", json={"name": "B"})
    await client.post("/workspaces", json={"name": "C"}, headers={"X-TWYF-Source": "hacker"})
    response = await client.post("/workspaces", json={"name": "D"}, headers={"X-Request-Id": "req-123"})
    assert response.headers["X-Request-Id"] == "req-123"
    rows = (
        _db(settings)
        .execute("SELECT source, client, request_id FROM app_events WHERE event_type = 'workspace.created' ORDER BY id")
        .fetchall()
    )
    assert [(r["source"], r["client"]) for r in rows[-4:]] == [
        ("ui", "browser"),
        ("api", None),
        ("api", None),
        ("api", None),
    ]
    assert rows[-1]["request_id"] == "req-123"


async def test_list_events_filters(client: httpx.AsyncClient) -> None:
    ws = await _ws(client)
    other = (await client.post("/workspaces", json={"name": "Other"})).json()["id"]
    events = (await client.get("/events", params={"workspace": ws, "limit": 1000})).json()
    assert events and all(e["workspaceId"] == ws for e in events)
    assert [e["id"] for e in events] == sorted(e["id"] for e in events)
    typed = (await client.get("/events", params={"type": "workspace.created"})).json()
    assert {e["workspaceId"] for e in typed} == {ws, other}
    after = (await client.get("/events", params={"after": events[0]["id"], "limit": 2})).json()
    assert len(after) == 2 and all(e["id"] > events[0]["id"] for e in after)
    assert (await client.get("/events", params={"question": "q_nope"})).json() == []


async def test_static_dir(settings: Settings, tmp_path: Path) -> None:
    static = tmp_path / "site"
    static.mkdir()
    (static / "index.html").write_text("<h1>twyf</h1>")
    app = build_app(settings.model_copy(update={"static_dir": static}), jobs=InlineJobs())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        assert "<h1>twyf</h1>" in (await client.get("/")).text
        assert (await client.get("/api/v1/health")).json()["status"] == "ok"


async def test_upload_returns_before_ingestion(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()

    class SlowParser:
        name = "slow"
        version = "1"

        def supports(self, file_type: str) -> bool:
            return True

        def parse(self, path: Path, file_type: str) -> list[ParsedDocument]:
            gate.wait(5)
            return [ParsedDocument("text", [ParsedBlock("paragraph", "Paragraph 1", path.read_text())])]

    monkeypatch.setattr(ingest_module, "pick_parser", lambda s, t: SlowParser())
    jobs = ThreadJobs()
    app = build_app(settings, jobs=jobs)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as client,
    ):
        ws = await _ws(client)
        item = await _upload(client, ws, "slow.txt", b"Takes a while.")
        assert item["status"] == "processing"
        gate.set()
        jobs.join()
        assert (await client.get(f"/workspaces/{ws}/files")).json()[0]["status"] == "ready"


async def test_ingestion_resumed_at_start(settings: Settings) -> None:
    class NoJobs:
        def submit(self, fn: object) -> None:
            return None

        def join(self) -> None:
            return None

    first = build_app(settings, jobs=NoJobs())
    async with (
        first.router.lifespan_context(first),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=first), base_url="http://test/api/v1") as client,
    ):
        ws = await _ws(client)
        item = await _upload(client, ws, "later.txt", b"Ingested at the next start.")
        assert item["status"] == "processing"
    second = build_app(settings, jobs=InlineJobs())
    async with (
        second.router.lifespan_context(second),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=second), base_url="http://test/api/v1") as client,
    ):
        assert (await client.get(f"/workspaces/{ws}/files")).json()[0]["status"] == "ready"
        assert len((await client.get("/workspaces")).json()) == 1


async def test_add_file_version_api(client: httpx.AsyncClient) -> None:
    ws = await _ws(client)
    item = await _upload(client, ws, "plan.txt", b"First draft.")
    note = (await client.post(f"/workspaces/{ws}/notes", json={"fileId": item["id"], "text": "Draft one"})).json()
    response = await client.post(
        f"/workspaces/{ws}/files/{item['id']}/versions", files={"file": ("plan-2.txt", b"Second draft.")}
    )
    updated = response.json()
    assert (updated["id"], updated["version"], updated["name"]) == (item["id"], 2, "plan-2.txt")
    [listed] = (await client.get(f"/workspaces/{ws}/notes")).json()
    assert (listed["id"], listed["fileVersion"]) == (note["id"], 1)


async def test_renames_and_edits(client: httpx.AsyncClient, settings: Settings) -> None:
    ws = await _ws(client)
    agent = (await client.get(f"/workspaces/{ws}/agents")).json()[0]
    session = (await client.post(f"/workspaces/{ws}/sessions", json={"title": "Old title"})).json()
    item = await _upload(client, ws, "a.txt", b"The lease ends on 30 June 2029.")
    note = (await client.post(f"/workspaces/{ws}/notes", json={"fileId": item["id"], "text": "Old text"})).json()
    conn = _db(settings)
    before = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')").fetchone()[0]
    import asyncio

    await asyncio.sleep(0.01)
    assert (await client.patch(f"/workspaces/{ws}/agents/{agent['id']}", json={"name": "Reader"})).json()[
        "name"
    ] == "Reader"
    assert (await client.patch(f"/workspaces/{ws}/sessions/{session['id']}", json={"title": "New title"})).json()[
        "title"
    ] == "New title"
    assert (await client.patch(f"/workspaces/{ws}/notes/{note['id']}", json={"text": "New text"})).json()[
        "text"
    ] == "New text"
    assert (await client.get(f"/workspaces/{ws}/agents")).json()[0]["name"] == "Reader"
    assert (await client.get(f"/workspaces/{ws}/sessions")).json()[0]["title"] == "New title"
    assert (await client.get(f"/workspaces/{ws}/notes")).json()[0]["text"] == "New text"
    for table, key, value, column in (
        ("agent_versions", agent["id"], "Translator 1", "name"),
        ("session_versions", session["id"], "Old title", "title"),
        ("note_versions", note["id"], "Old text", "text"),
    ):
        key_col = {"agent_versions": "agent_id", "session_versions": "session_id", "note_versions": "note_id"}[table]
        row = versioned.as_of(conn, table, key_col, key, before)
        assert row is not None and row[column] == value
    orchestrator = agents.builtin(conn, ws, "orchestrator").id
    translator = agent["id"]
    from twyf.recording.context import RequestContext

    ctx = RequestContext(actor_id="u_local", source="api", user_id="u_local", request_id="t")
    agent_note_id = agent_note(
        conn,
        ctx,
        ws,
        item["id"],
        "Ends 2029",
        [cite(conn, ctx, ws, item["id"], "30 June 2029", translator)],
        translator,
    )
    response = await client.patch(f"/workspaces/{ws}/notes/{agent_note_id}", json={"text": "Changed"})
    assert response.status_code == 400 and response.json()["error"]["code"] == "validation"
    response = await client.patch(f"/workspaces/{ws}/agents/{orchestrator}", json={"name": "Boss"})
    assert response.status_code == 400 and response.json()["error"]["code"] == "validation"
    assert not [op for op in OPERATIONS if "rename" in op.name and "file" in op.name]
    assert not [op for op in OPERATIONS if op.method == "PATCH" and "/files/" in op.path]


async def test_soft_deletes(client: httpx.AsyncClient, settings: Settings) -> None:
    ws = await _ws(client)
    conn = _db(settings)
    from twyf.recording.context import RequestContext

    ctx = RequestContext(actor_id="u_local", source="api", user_id="u_local", request_id="t")
    keep = await _upload(client, ws, "keep.txt", b"The lease ends on 30 June 2029.")
    gone = await _upload(client, ws, "gone.txt", b"Rent rises by eight percent a year.")
    session = (await client.post(f"/workspaces/{ws}/sessions", json={"title": "S"})).json()
    agent = (await client.post(f"/workspaces/{ws}/agents", json={"name": "Temp", "specialty": "generic"})).json()
    by_agent = agent_note(
        conn,
        ctx,
        ws,
        keep["id"],
        "Ends 2029",
        [cite(conn, ctx, ws, keep["id"], "30 June 2029", agent["id"])],
        agent["id"],
    )
    on_gone = (await client.post(f"/workspaces/{ws}/notes", json={"fileId": gone["id"], "text": "About rent"})).json()
    user_note = (await client.post(f"/workspaces/{ws}/notes", json={"fileId": keep["id"], "text": "Mine"})).json()
    gone_citation = cite(conn, ctx, ws, gone["id"], "eight percent a year", agent["id"])
    with transaction(conn):
        sessions.add_message(conn, ctx, workspace_id=ws, session_id=session["id"], role="assistant",
                             text="Rent rises [1].", citation_ids=[gone_citation])  # fmt: skip
    kept_session = (await client.post(f"/workspaces/{ws}/sessions", json={"title": "Kept"})).json()
    with transaction(conn):
        sessions.add_message(conn, ctx, workspace_id=ws, session_id=kept_session["id"], role="assistant",
                             text="Rent rises [1].", citation_ids=[gone_citation])  # fmt: skip

    assert (await client.delete(f"/workspaces/{ws}/files/{gone['id']}")).status_code == 204
    assert (await client.delete(f"/workspaces/{ws}/agents/{agent['id']}")).status_code == 204
    assert (await client.delete(f"/workspaces/{ws}/notes/{user_note['id']}")).status_code == 204
    assert (await client.delete(f"/workspaces/{ws}/sessions/{session['id']}")).status_code == 204

    assert [f["id"] for f in (await client.get(f"/workspaces/{ws}/files")).json()] == [keep["id"]]
    assert agent["id"] not in [a["id"] for a in (await client.get(f"/workspaces/{ws}/agents")).json()]
    listed_notes = (await client.get(f"/workspaces/{ws}/notes")).json()
    assert [n["id"] for n in listed_notes] == [by_agent]
    assert on_gone["id"] not in [n["id"] for n in listed_notes]
    assert listed_notes[0]["authorName"] == "Temp"
    assert session["id"] not in [s["id"] for s in (await client.get(f"/workspaces/{ws}/sessions")).json()]
    [message] = (await client.get(f"/workspaces/{ws}/sessions/{kept_session['id']}/messages")).json()
    assert message["citations"][0]["fileName"] == "gone.txt"

    for method, path in (
        ("DELETE", f"/files/{gone['id']}"), ("POST", f"/files/{gone['id']}/versions"),
        ("PATCH", f"/agents/{agent['id']}"), ("DELETE", f"/notes/{user_note['id']}"),
        ("GET", f"/sessions/{session['id']}/messages"),
    ):  # fmt: skip
        kwargs: dict[str, Any] = {}
        if method == "PATCH":
            kwargs["json"] = {"name": "x"}
        if path.endswith("/versions"):
            kwargs["files"] = {"file": ("x.txt", b"x")}
        response = await client.request(method, f"/workspaces/{ws}{path}", **kwargs)
        assert response.status_code == 404, path
    for table, key in (
        ("files", gone["id"]),
        ("agents", agent["id"]),
        ("notes", user_note["id"]),
        ("sessions", session["id"]),
    ):
        assert conn.execute(f"SELECT deleted_at FROM {table} WHERE id = ?", (key,)).fetchone()[0] is not None

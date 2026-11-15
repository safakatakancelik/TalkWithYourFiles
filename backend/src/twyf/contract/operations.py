"""The whole surface of the system. HTTP routes and MCP tools are both generated from OPERATIONS."""

import importlib
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from twyf.contract.base import Opt, Wire
from twyf.contract.events import AgentEvent
from twyf.contract.models import (
    Agent,
    ChatMsg,
    ContextMap,
    EventRecord,
    FileItem,
    FileText,
    Note,
    Session,
    SubmitResult,
    TranslatorReply,
    Weight,
    Workspace,
)
from twyf.contract.turns import TurnOffer, Usage


class Operation(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str  # snake_case. Also the MCP tool name
    method: Literal["GET", "POST", "PATCH", "DELETE"]
    path: str  # under /api/v1, for example "/workspaces/{ws}/files"
    input: type[Wire] | None  # path, query and body fields in one model
    output: Any  # a Wire model, list[Wire] or None
    handler: str  # "twyf.services.files:upload". A string, so contract/ imports nothing
    kind: Literal["json", "upload", "stream"] = "json"
    backend_method: str | None  # the method on the TypeScript Backend interface, when there is one
    description: str  # shown as the MCP tool description


# Input models, one per operation


class ListWorkspacesInput(Wire):
    pass


class CreateWorkspaceInput(Wire):
    name: str


class RenameWorkspaceInput(Wire):
    ws: str
    name: str


class DeleteWorkspaceInput(Wire):
    ws: str


class ListFilesInput(Wire):
    ws: str


class UploadFileInput(Wire):
    ws: str


class AddFileVersionInput(Wire):
    ws: str
    file_id: str


class DeleteFileInput(Wire):
    ws: str
    file_id: str


class GetFileTextInput(Wire):
    ws: str
    file_id: str
    start: Opt[int] = None
    end: Opt[int] = None


class ListAgentsInput(Wire):
    ws: str


class CreateAgentInput(Wire):
    ws: str
    name: str
    specialty: str


class RenameAgentInput(Wire):
    ws: str
    agent_id: str
    name: str


class DeleteAgentInput(Wire):
    ws: str
    agent_id: str


class ListNotesInput(Wire):
    ws: str


class AddNoteInput(Wire):
    ws: str
    file_id: str
    text: str


class EditNoteInput(Wire):
    ws: str
    note_id: str
    text: str


class DeleteNoteInput(Wire):
    ws: str
    note_id: str


class SetNoteWeightInput(Wire):
    ws: str
    note_ids: list[str]
    weight: Weight


class ListSessionsInput(Wire):
    ws: str


class CreateSessionInput(Wire):
    ws: str
    title: str


class RenameSessionInput(Wire):
    ws: str
    session_id: str
    title: str


class DeleteSessionInput(Wire):
    ws: str
    session_id: str


class GetMessagesInput(Wire):
    ws: str
    session_id: str


class GetContextMapInput(Wire):
    ws: str


class AskInput(Wire):
    ws: str
    session_id: str
    question: str


class GetQuestionEventsInput(Wire):
    ws: str
    question_id: str
    after: Opt[int] = None


class CancelQuestionInput(Wire):
    ws: str
    question_id: str


class AskTranslatorInput(Wire):
    ws: str
    agent_id: str
    question: str


class ListEventsInput(Wire):
    workspace: Opt[str] = None
    question: Opt[str] = None
    type: Opt[str] = None
    after: Opt[int] = None
    limit: int = Field(default=200)


class ClaimTurnInput(Wire):
    worker: str
    wait_s: int = Field(default=25)


class SubmitTurnInput(Wire):
    turn_id: str
    lease_token: str
    output: dict[str, Any]
    usage: Opt[Usage] = None


class FailTurnInput(Wire):
    turn_id: str
    lease_token: str
    reason: str


def _op(
    name: str,
    method: Literal["GET", "POST", "PATCH", "DELETE"],
    path: str,
    input: type[Wire],
    output: Any,
    handler: str,
    backend_method: str | None,
    description: str,
    kind: Literal["json", "upload", "stream"] = "json",
) -> Operation:
    return Operation(
        name=name,
        method=method,
        path=path,
        input=input,
        output=output,
        handler="twyf.services." + handler,
        kind=kind,
        backend_method=backend_method,
        description=description,
    )


WS = "/workspaces/{ws}"

OPERATIONS: list[Operation] = [
    _op("list_workspaces", "GET", "/workspaces", ListWorkspacesInput, list[Workspace], "workspaces:list",
        "listWorkspaces", "List the user's workspaces."),
    _op("create_workspace", "POST", "/workspaces", CreateWorkspaceInput, Workspace, "workspaces:create",
        "createWorkspace", "Create a workspace with its orchestrator, verifier, chat agent and two translators."),
    _op("rename_workspace", "PATCH", WS, RenameWorkspaceInput, Workspace, "workspaces:rename",
        "renameWorkspace", "Rename a workspace."),
    _op("delete_workspace", "DELETE", WS, DeleteWorkspaceInput, None, "workspaces:delete",
        "deleteWorkspace", "Delete a workspace. Running questions in it are cancelled. Nothing is removed."),
    _op("list_files", "GET", WS + "/files", ListFilesInput, list[FileItem], "files:list",
        "listFiles", "List the files of a workspace with their status and current version."),
    _op("upload_file", "POST", WS + "/files", UploadFileInput, FileItem, "files:upload",
        "uploadFile", "Upload a new file. Returns at once with status processing.", kind="upload"),
    _op("add_file_version", "POST", WS + "/files/{file_id}/versions", AddFileVersionInput, FileItem,
        "files:add_version", "addFileVersion",
        "Add new content to an existing file as its next version. Its notes stay with it.", kind="upload"),
    _op("delete_file", "DELETE", WS + "/files/{file_id}", DeleteFileInput, None, "files:delete",
        "deleteFile", "Delete a file and hide its notes. The stored content is kept."),
    _op("get_file_text", "GET", WS + "/files/{file_id}/text", GetFileTextInput, FileText, "files:get_text",
        None, "Read the extracted text of a file's current version, optionally a character range."),
    _op("list_agents", "GET", WS + "/agents", ListAgentsInput, list[Agent], "agents:list",
        "listAgents", "List the translators of a workspace."),
    _op("create_agent", "POST", WS + "/agents", CreateAgentInput, Agent, "agents:create",
        "createAgent", "Add a translator with a name and a speciality to the workspace's pool."),
    _op("rename_agent", "PATCH", WS + "/agents/{agent_id}", RenameAgentInput, Agent, "agents:rename",
        "renameAgent", "Rename a translator."),
    _op("delete_agent", "DELETE", WS + "/agents/{agent_id}", DeleteAgentInput, None, "agents:delete",
        "deleteAgent", "Delete a translator. Its notes stay."),
    _op("list_notes", "GET", WS + "/notes", ListNotesInput, list[Note], "notes:list",
        "listNotes", "List every note in a workspace, from all versions of each file."),
    _op("add_note", "POST", WS + "/notes", AddNoteInput, Note, "notes:add",
        "addNote", "Add a note written by the user about a file."),
    _op("edit_note", "PATCH", WS + "/notes/{note_id}", EditNoteInput, Note, "notes:edit",
        "editNote", "Edit the text of a note written by the user."),
    _op("delete_note", "DELETE", WS + "/notes/{note_id}", DeleteNoteInput, None, "notes:delete",
        "deleteNote", "Delete a note."),
    _op("set_note_weight", "POST", WS + "/notes/weight", SetNoteWeightInput, None, "notes:set_weight",
        "setNoteWeight", "Set how much later work relies on these notes: off, low, normal or high."),
    _op("list_sessions", "GET", WS + "/sessions", ListSessionsInput, list[Session], "sessions:list",
        "listSessions", "List the chat sessions of a workspace, latest first."),
    _op("create_session", "POST", WS + "/sessions", CreateSessionInput, Session, "sessions:create",
        "createSession", "Start a chat session."),
    _op("rename_session", "PATCH", WS + "/sessions/{session_id}", RenameSessionInput, Session, "sessions:rename",
        "renameSession", "Rename a chat session."),
    _op("delete_session", "DELETE", WS + "/sessions/{session_id}", DeleteSessionInput, None, "sessions:delete",
        "deleteSession", "Delete a chat session."),
    _op("get_messages", "GET", WS + "/sessions/{session_id}/messages", GetMessagesInput, list[ChatMsg],
        "sessions:messages", "getMessages", "Read the messages of a chat session, with their citations."),
    _op("get_context_map", "GET", WS + "/context-map", GetContextMapInput, ContextMap, "contextmap:get",
        "getContextMap", "Read the workspace's map of files, entities and links."),
    _op("ask", "POST", WS + "/sessions/{session_id}/questions", AskInput, AgentEvent, "questions:ask",
        "ask", "Ask a question. Agents answer it together and every claim is verified before it is returned.",
        kind="stream"),
    _op("get_question_events", "GET", WS + "/questions/{question_id}/events", GetQuestionEventsInput, AgentEvent,
        "questions:events", None, "Read the events of a question after a given event id.", kind="stream"),
    _op("cancel_question", "POST", WS + "/questions/{question_id}/cancel", CancelQuestionInput, None,
        "questions:cancel", "ask", "Cancel a running question."),
    _op("ask_translator", "POST", WS + "/agents/{agent_id}/ask", AskTranslatorInput, TranslatorReply,
        "agents:ask_translator", "askTranslator", "Ask one translator directly. Its reply is cited but not verified."),
    _op("list_events", "GET", "/events", ListEventsInput, list[EventRecord], "events:list_events",
        None, "Read the event log, filtered by workspace, question, type and id."),
    _op("claim_turn", "POST", "/runtime/turns/claim", ClaimTurnInput, TurnOffer | None, "turns:claim",
        None, "Claim the oldest queued agent turn. Waits up to wait_s seconds for one."),
    _op("submit_turn", "POST", "/runtime/turns/{turn_id}/submit", SubmitTurnInput, SubmitResult, "turns:submit",
        None, "Submit the output of a claimed turn."),
    _op("fail_turn", "POST", "/runtime/turns/{turn_id}/fail", FailTurnInput, None, "turns:fail",
        None, "Give up on a claimed turn with a reason."),
]  # fmt: skip

_BY_NAME = {op.name: op for op in OPERATIONS}


def get_operation(name: str) -> Operation:
    return _BY_NAME[name]


def resolve_handler(op: Operation) -> Callable[..., Any]:
    module_name, _, attr = op.handler.partition(":")
    handler = getattr(importlib.import_module(module_name), attr)
    if not callable(handler):
        raise TypeError(f"{op.handler} is not callable")
    return handler

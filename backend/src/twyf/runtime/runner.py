"""Runs one turn: renders the prompt, records the turn, calls the runtime, validates, retries."""

import asyncio
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from twyf import logging_setup
from twyf.agents.definitions import current_version, load_folder
from twyf.agents.prompts import render
from twyf.config import Settings
from twyf.contract.base import Wire
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import turns as repo
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.runtime.base import AgentRuntime, Attachment, RuntimeError_, TurnRequest, TurnResult

type ConnFactory = Callable[[], sqlite3.Connection]


class TurnFailed(Exception):
    def __init__(self, turn_type: str, agent_id: str, reason: str) -> None:
        super().__init__(f"{turn_type} turn of {agent_id} failed: {reason}")
        self.turn_type = turn_type
        self.agent_id = agent_id
        self.reason = reason


def _agent(conn: sqlite3.Connection, agent_id: str) -> agents_repo.AgentRow:
    row = conn.execute("SELECT workspace_id FROM agents WHERE id = ?", (agent_id,)).fetchone()
    agent = agents_repo.get(conn, row["workspace_id"], agent_id) if row is not None else None
    if agent is None:
        raise TurnFailed("?", agent_id, "unknown agent")
    return agent


class TurnRunner:
    def __init__(self, runtime: AgentRuntime, settings: Settings, conn_factory: ConnFactory) -> None:
        self.runtime = runtime
        self.settings = settings
        self.conn_factory = conn_factory

    def _rules(self) -> str:
        return load_folder(self.settings.agents_dir).rules

    async def run[T: Wire](
        self,
        ctx: RequestContext,
        *,
        agent_id: str,
        turn_type: str,
        input: Wire,
        output_model: type[T],
        validate: Callable[[T], list[str]] | None = None,
        attachments: list[Attachment] | None = None,
        question_id: str | None = None,
        round_id: str | None = None,
    ) -> tuple[T, str]:
        """Returns the validated output and the turn id. Raises TurnFailed after the last retry."""
        error: str | None = None
        retry_of: str | None = None
        rules = await asyncio.to_thread(self._rules)
        for attempt in range(1, self.settings.max_turn_retries + 2):
            attempt_input = input.model_copy(update={"previous_error": error}) if error else input
            turn_id = new_id("t")
            request, agent_ctx, definition_version_id, workspace_id = await asyncio.to_thread(
                self._queue, ctx, agent_id, turn_type, attempt_input, output_model, attachments or [], attempt,
                retry_of, question_id, round_id, rules, turn_id,
            )  # fmt: skip
            started = time.monotonic()
            logging_setup.turn_id.set(turn_id)
            try:
                async with asyncio.timeout(self.settings.turn_timeout_s):
                    result = await self.runtime.run_turn(request)
            except asyncio.CancelledError:
                await asyncio.to_thread(self._end, agent_ctx, workspace_id, turn_id, definition_version_id, "cancelled",
                                        "cancelled", question_id, round_id)  # fmt: skip
                raise
            except TimeoutError:
                error = f"the turn took longer than {self.settings.turn_timeout_s} seconds"
                await asyncio.to_thread(self._end, agent_ctx, workspace_id, turn_id, definition_version_id, "timed_out",
                                        error, question_id, round_id)  # fmt: skip
                retry_of = turn_id
                continue
            except RuntimeError_ as failure:
                error = str(failure)
                if failure.code == "cancelled":
                    await asyncio.to_thread(self._end, agent_ctx, workspace_id, turn_id, definition_version_id,
                                            "cancelled", error, question_id, round_id)  # fmt: skip
                    raise TurnFailed(turn_type, agent_id, error) from failure
                state = "timed_out" if failure.code == "timeout" else "failed"
                await asyncio.to_thread(self._end, agent_ctx, workspace_id, turn_id, definition_version_id, state,
                                        error, question_id, round_id)  # fmt: skip
                retry_of = turn_id
                continue
            duration_ms = int((time.monotonic() - started) * 1000)
            parsed, problems = self._validate(result, output_model, validate)
            if parsed is None or problems:
                error = "; ".join(problems)
                await asyncio.to_thread(self._end, agent_ctx, workspace_id, turn_id, definition_version_id, "failed",
                                        error, question_id, round_id, result.output)  # fmt: skip
                retry_of = turn_id
                continue
            await asyncio.to_thread(
                self._done, agent_ctx, workspace_id, turn_id, definition_version_id, result, duration_ms, question_id,
                round_id,
            )  # fmt: skip
            return parsed, turn_id
        raise TurnFailed(turn_type, agent_id, error or "no attempt succeeded")

    @staticmethod
    def _validate[T: Wire](
        result: TurnResult, output_model: type[T], validate: Callable[[T], list[str]] | None
    ) -> tuple[T | None, list[str]]:
        try:
            parsed = output_model.model_validate(result.output)
        except ValidationError as invalid:
            return None, [
                f"output does not match the schema: {invalid.error_count()} errors: {invalid.errors(include_url=False)}"
            ]
        return parsed, validate(parsed) if validate is not None else []

    def _queue(
        self, ctx: RequestContext, agent_id: str, turn_type: str, input: Wire, output_model: type[Wire],
        attachments: list[Attachment], attempt: int, retry_of: str | None, question_id: str | None,
        round_id: str | None, rules: str, turn_id: str,
    ) -> tuple[TurnRequest, RequestContext, int, str]:  # fmt: skip
        conn = self.conn_factory()
        try:
            agent = _agent(conn, agent_id)
            definition = current_version(conn, agent.definition_id)
            skills = {s.slug: s for s in definition.skills}
            system_prompt, instructions = render(agent, definition, turn_type, skills, rules=rules)
            data: dict[str, Any] = input.model_dump(mode="json", by_alias=True, exclude_none=True)
            agent_ctx = ctx.as_actor(agent_id)
            with transaction(conn):
                repo.insert(
                    conn, turn_id=turn_id, workspace_id=agent.workspace_id, question_id=question_id, round_id=round_id,
                    agent_id=agent_id, agent_version_id=agent.agent_version_id, definition_version_id=definition.id,
                    turn_type=turn_type, attempt=attempt, retry_of=retry_of, runtime=self.runtime.name,
                    system_prompt=system_prompt, input=data,
                )  # fmt: skip
                record(
                    conn, agent_ctx, "turn.queued", workspace_id=agent.workspace_id, question_id=question_id,
                    round_id=round_id, turn_id=turn_id, entity_type="turn", entity_id=turn_id,
                    payload={"turn_type": turn_type, "attempt": attempt, "retry_of": retry_of},
                    definition_version_id=definition.id,
                )  # fmt: skip
                repo.mark_started(conn, turn_id)
            request = TurnRequest(
                turn_id=turn_id, turn_type=turn_type, agent_name=agent.name, agent_kind=agent.agent_kind,
                system_prompt=system_prompt, instructions=instructions, input=data,
                output_schema=output_model.model_json_schema(by_alias=True), attachments=attachments,
                timeout_s=self.settings.turn_timeout_s,
            )  # fmt: skip
            return request, agent_ctx, definition.id, agent.workspace_id
        finally:
            conn.close()

    def _end(
        self, ctx: RequestContext, workspace_id: str, turn_id: str, definition_version_id: int, state: str, error: str,
        question_id: str | None, round_id: str | None, output: dict[str, Any] | None = None,
    ) -> None:  # fmt: skip
        event = {"failed": "turn.failed", "timed_out": "turn.timed_out", "cancelled": "turn.cancelled"}[state]
        conn = self.conn_factory()
        try:
            with transaction(conn):
                repo.finish(conn, turn_id, state=state, output=output, error=error)
                record(
                    conn, ctx, event, workspace_id=workspace_id, question_id=question_id, round_id=round_id,
                    turn_id=turn_id, entity_type="turn", entity_id=turn_id, payload={"error": error},
                    definition_version_id=definition_version_id,
                )  # fmt: skip
        finally:
            conn.close()

    def _done(
        self, ctx: RequestContext, workspace_id: str, turn_id: str, definition_version_id: int, result: TurnResult,
        duration_ms: int, question_id: str | None, round_id: str | None,
    ) -> None:  # fmt: skip
        usage = result.usage
        conn = self.conn_factory()
        try:
            with transaction(conn):
                repo.finish(
                    conn, turn_id, state="done", output=result.output, model=usage.model,
                    input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, duration_ms=duration_ms,
                )  # fmt: skip
                record(
                    conn, ctx, "turn.completed", workspace_id=workspace_id, question_id=question_id, round_id=round_id,
                    turn_id=turn_id, entity_type="turn", entity_id=turn_id,
                    payload={"model": usage.model, "input_tokens": usage.input_tokens,
                             "output_tokens": usage.output_tokens, "duration_ms": duration_ms},
                    definition_version_id=definition_version_id,
                )  # fmt: skip
        finally:
            conn.close()

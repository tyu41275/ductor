"""``/compact``: compact the active CLI session in place."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from ductor_bot.cli.types import AgentResponse
from ductor_bot.i18n import t
from ductor_bot.orchestrator.compact import compact_prompt
from ductor_bot.orchestrator.core import Orchestrator
from ductor_bot.orchestrator.flows import normal
from ductor_bot.session.key import SessionKey

KEY = SessionKey(chat_id=1)


def _resp(**kwargs: Any) -> AgentResponse:
    base: dict[str, Any] = {"result": "ok", "session_id": "sess-1", "is_error": False}
    base.update(kwargs)
    return AgentResponse(**base)


async def _session(orch: Orchestrator, sid: str = "sess-1") -> AsyncMock:
    object.__setattr__(orch._cli_service, "execute", AsyncMock(return_value=_resp(session_id=sid)))
    await normal(orch, KEY, "Setup")
    compact = AsyncMock(return_value=_resp(result="", session_id=sid))
    object.__setattr__(orch._cli_service, "execute", compact)
    return compact


def test_compact_prompt_is_the_bare_slash_command() -> None:
    assert compact_prompt() == "/compact"
    assert compact_prompt("  keep the   DH decisions ") == "/compact keep the DH decisions"


async def test_compacts_the_existing_session_without_hooks(orch: Orchestrator) -> None:
    execute = await _session(orch)
    status = await orch.compact_active_session(KEY)
    assert status == t("compact.done")
    request = execute.await_args.args[0]
    assert request.prompt == "/compact"
    assert request.resume_session == "sess-1"
    assert request.append_system_prompt is None
    session = await orch._sessions.get_active(KEY)
    assert session is not None
    assert session.session_id == "sess-1"


async def test_instructions_are_passed_to_compact(orch: Orchestrator) -> None:
    execute = await _session(orch)
    await orch.compact_active_session(KEY, "focus on open tasks")
    assert execute.await_args.args[0].prompt == "/compact focus on open tasks"


async def test_no_session_does_not_call_the_cli(orch: Orchestrator) -> None:
    execute = AsyncMock()
    object.__setattr__(orch._cli_service, "execute", execute)
    assert await orch.compact_active_session(KEY) == t("compact.no_session")
    execute.assert_not_awaited()


async def test_non_claude_session_is_refused(orch: Orchestrator) -> None:
    execute = await _session(orch)
    session = await orch._sessions.get_active(KEY)
    assert session is not None
    import copy

    codex_session = copy.copy(session)
    object.__setattr__(codex_session, "provider", "codex")
    object.__setattr__(orch._sessions, "get_active", AsyncMock(return_value=codex_session))
    execute.reset_mock()
    status = await orch.compact_active_session(KEY)
    assert status == t("compact.unsupported", provider="codex")
    execute.assert_not_awaited()


async def test_cli_error_is_reported(orch: Orchestrator) -> None:
    execute = await _session(orch)
    execute.return_value = _resp(is_error=True, result="boom")
    assert await orch.compact_active_session(KEY) == t("compact.failed", error="boom")

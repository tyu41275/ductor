"""``/compact``: compact the active CLI session in place.

Claude Code accepts ``/compact [instructions]`` as a headless prompt on a resumed
session and writes a ``compact_boundary`` into the same session (verified with
``claude -p "/compact" --resume <id>``). The prompt is sent as-is: no hooks, no
appended system prompt, so the CLI sees the slash command and nothing else.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ductor_bot.cli.types import AgentRequest
from ductor_bot.config import resolve_timeout
from ductor_bot.i18n import t

if TYPE_CHECKING:
    from ductor_bot.orchestrator.core import Orchestrator
    from ductor_bot.session import SessionKey

logger = logging.getLogger(__name__)

COMPACT_PROVIDERS = frozenset({"claude"})


def compact_prompt(instructions: str = "") -> str:
    extra = " ".join(instructions.split())
    return f"/compact {extra}" if extra else "/compact"


async def compact_session(orch: Orchestrator, key: SessionKey, instructions: str = "") -> str:
    """Compact the session behind *key*; return the user-facing status line."""
    session = await orch._sessions.get_active(key)
    if session is None:
        return t("compact.no_session")
    if session.provider not in COMPACT_PROVIDERS:
        return t("compact.unsupported", provider=session.provider)
    if not session.session_id:
        return t("compact.no_session")
    request = AgentRequest(
        prompt=compact_prompt(instructions),
        model_override=session.model,
        provider_override=session.provider,
        effort_override=session.reasoning_effort,
        chat_id=key.chat_id,
        topic_id=key.topic_id,
        transport=key.transport,
        resume_session=session.session_id,
        timeout_seconds=resolve_timeout(orch._config, "normal"),
    )
    logger.info("Compacting session sid=%s", session.session_id[:8])
    response = await orch._cli_service.execute(request)
    if response.is_error or response.timed_out:
        logger.warning("Compact failed sid=%s: %s", session.session_id[:8], response.result[:200])
        return t("compact.failed", error=(response.result or "unknown error")[:300])
    return t("compact.done")

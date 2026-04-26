"""High-level chat service driving Anthropic's Claude with tool use.

The service owns the agent loop: send the user message, execute any
tool calls Claude requests, send the tool results back, and iterate
until Claude returns a plain text answer (or we hit the safety cap of
8 tool turns).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from runllm.llm.exceptions import LLMError, LLMToolError
from runllm.llm.prompt_builder import build_system_prompt
from runllm.llm.tools import TOOL_SCHEMAS, ToolRegistry
from runllm.models import Activity, User
from runllm.processing.storage import ActivityStorage

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]

DEFAULT_MAX_TURNS = 8
DEFAULT_MAX_TOKENS = 4_096
DEFAULT_LOOKBACK_DAYS = 365


@dataclass(slots=True)
class ChatResponse:
    """Final response returned to the API layer."""

    response: str
    tools_used: list[str] = field(default_factory=list)


class LLMService:
    """Run a single chat turn against Claude with tool use."""

    def __init__(
        self,
        anthropic_client: Any,
        storage: ActivityStorage,
        session_factory: SessionFactory,
        *,
        model: str = "claude-sonnet-4-5",
        max_turns: int = DEFAULT_MAX_TURNS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._client = anthropic_client
        self._storage = storage
        self._session_factory = session_factory
        self._model = model
        self._max_turns = max_turns
        self._max_tokens = max_tokens

    async def chat(self, user_id: UUID, message: str) -> ChatResponse:
        user, activities = await self._load_user_and_activities(user_id)
        system_prompt = build_system_prompt(user, activities)
        registry = ToolRegistry(user_id, self._session_factory, self._storage)

        messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
        tools_used: list[str] = []

        for turn in range(self._max_turns):
            response = await self._create_message(system_prompt, messages)
            stop_reason = getattr(response, "stop_reason", None)
            blocks = list(getattr(response, "content", []))

            if stop_reason != "tool_use":
                return ChatResponse(
                    response=_extract_text(blocks),
                    tools_used=tools_used,
                )

            messages.append({"role": "assistant", "content": _serialize_blocks(blocks)})
            tool_results: list[dict[str, Any]] = []
            for block in blocks:
                if getattr(block, "type", None) != "tool_use":
                    continue
                name = block.name
                tool_input = block.input or {}
                tools_used.append(name)
                logger.info("tool_use turn=%d tool=%s args=%s", turn, name, tool_input)
                try:
                    result = await registry.dispatch(name, tool_input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
                except LLMToolError as exc:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": True,
                            "content": str(exc),
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

        raise LLMError(f"tool turn limit ({self._max_turns}) exceeded")

    # ------------------------------------------------------------------ helpers

    async def _create_message(self, system_prompt: str, messages: list[dict[str, Any]]) -> Any:
        return await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

    async def _load_user_and_activities(self, user_id: UUID) -> tuple[User, list[Activity]]:
        async with self._session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise LLMError(f"user {user_id} not found")
            threshold = datetime.now(tz=UTC) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
            stmt = (
                select(Activity)
                .where(Activity.user_id == user_id, Activity.start_time >= threshold)
                .order_by(Activity.start_time)  # type: ignore[arg-type]
            )
            activities = (await session.exec(stmt)).all()
        return user, list(activities)


def _extract_text(blocks: list[Any]) -> str:
    out: list[str] = []
    for block in blocks:
        if getattr(block, "type", None) == "text":
            out.append(block.text)
    return "\n".join(out).strip()


def _serialize_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    """Serialize Anthropic response blocks back into request-format dicts."""

    payload: list[dict[str, Any]] = []
    for block in blocks:
        kind = getattr(block, "type", None)
        if kind == "text":
            payload.append({"type": "text", "text": block.text})
        elif kind == "tool_use":
            payload.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
    return payload

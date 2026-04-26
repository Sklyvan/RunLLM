"""Chat endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from runllm.api.auth import get_current_user
from runllm.api.dependencies import get_llm_service
from runllm.llm.service import LLMService
from runllm.models import User

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str


class ChatResponseBody(BaseModel):
    response: str
    tools_used: list[str]


@router.post("", response_model=ChatResponseBody)
async def chat(
    body: ChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> ChatResponseBody:
    result = await llm.chat(user.id, body.message)
    return ChatResponseBody(response=result.response, tools_used=result.tools_used)

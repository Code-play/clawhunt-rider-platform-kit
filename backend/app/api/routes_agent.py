"""Agent 会话端点（求职者端；会话 id 即会话令牌，支持 client_message_id 幂等重放）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agent import engine
from app.agent.llm import LLMClient
from app.api.deps import get_clock, get_db, get_llm, get_settings, get_vault
from app.config import Settings
from app.db.database import Database
from app.models.schemas import AgentMessageRequest, AgentSessionCreate
from app.security.vault import Vault

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/sessions", status_code=201)
async def create_session(
    body: AgentSessionCreate | None = None,
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
    llm: LLMClient = Depends(get_llm),
) -> dict:
    return await engine.create_session(
        db, clock, llm, candidate_id=body.candidate_id if body else None
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: AgentMessageRequest,
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
    llm: LLMClient = Depends(get_llm),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await engine.handle_message(
        db,
        vault,
        settings,
        clock,
        llm,
        session_id=session_id,
        text=body.text,
        client_message_id=body.client_message_id,
    )

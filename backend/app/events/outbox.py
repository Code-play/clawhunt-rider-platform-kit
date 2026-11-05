"""事务性 outbox：业务写入与事件写入同事务；去重键避免重复事件。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

VALID_EVENT_TYPES = {
    "candidate.created",
    "candidate.updated",
    "candidate.completed",
    "booking.created",
    "booking.cancelled",
    "handoff.requested",
}


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def default_dedupe_key(event_type: str, aggregate_id: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]
    return f"{event_type}:{aggregate_id}:{digest}"


async def emit_event(
    conn: asyncpg.Connection,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID | str,
    payload: dict[str, Any],
    dedupe_key: str | None = None,
    now: datetime | None = None,
) -> UUID | None:
    """写入 outbox；同一 dedupe_key 重复写入返回已存在事件 id（不重复发）。"""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    key = dedupe_key or default_dedupe_key(event_type, str(aggregate_id), payload)
    created_at = now or datetime.now(timezone.utc)
    row = await conn.fetchrow(
        """
        INSERT INTO outbox_events
            (event_type, aggregate_type, aggregate_id, payload, dedupe_key, next_attempt_at, created_at)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $6)
        ON CONFLICT (dedupe_key) DO NOTHING
        RETURNING id
        """,
        event_type,
        aggregate_type,
        aggregate_id,
        canonical_json(payload),
        key,
        created_at,
    )
    if row is not None:
        return row["id"]
    existing = await conn.fetchval("SELECT id FROM outbox_events WHERE dedupe_key = $1", key)
    return existing

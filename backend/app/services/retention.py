"""保留期与删除（未录用 90 天 / 对话原文 30 天 / 未成年人 24 小时）。

时间基准全部来自注入的 Clock；测试可冻结时钟，无需等待真实时间。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.services import audit


def _affected(result: str) -> int:
    """asyncpg execute() 返回 'UPDATE 3' / 'DELETE 5' 这类状态串。"""
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0


async def run_retention(db: Any, clock: Any, settings: Any, *, actor: str = "retention-worker") -> dict[str, Any]:
    now = clock.now()
    conversation_cutoff = now - timedelta(days=settings.retention_conversation_days)
    async with db.transaction() as conn:
        redacted_result = await conn.execute(
            """
            UPDATE agent_messages
            SET raw_text = NULL, redacted_at = $1
            WHERE raw_text IS NOT NULL AND created_at < $2
            """,
            now,
            conversation_cutoff,
        )
        redacted_messages = _affected(redacted_result)

        deleted_rows = await conn.fetch(
            """
            DELETE FROM candidates
            WHERE retention_until IS NOT NULL AND retention_until <= $1
            RETURNING id, is_minor
            """,
            now,
        )
        deleted_candidates = len(deleted_rows)
        deleted_minors = sum(1 for row in deleted_rows if row["is_minor"])

        await conn.execute(
            """
            INSERT INTO retention_runs (as_of, deleted_candidates, redacted_messages, run_at)
            VALUES ($1, $2, $3, $4)
            """,
            now,
            deleted_candidates,
            redacted_messages,
            now,
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="retention.run",
            resource="retention",
            payload={
                "as_of": now.isoformat(),
                "deleted_candidates": deleted_candidates,
                "deleted_minors": deleted_minors,
                "redacted_messages": redacted_messages,
            },
        )
        return {
            "as_of": now.isoformat(),
            "deleted_candidates": deleted_candidates,
            "deleted_minors": deleted_minors,
            "redacted_messages": redacted_messages,
            "conversation_cutoff": conversation_cutoff.isoformat(),
        }

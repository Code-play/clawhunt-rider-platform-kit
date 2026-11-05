"""只追加哈希链审计：每条记录 = hash(prev_hash | actor | action | resource | payload)。

- 触发器拒绝 UPDATE/DELETE（见 init.sql）；
- verify_chain() 重算全链，能定位到第一条被改动的行（返回 broken_at）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import asyncpg

GENESIS_HASH = "GENESIS"


def canonical_payload(payload: dict[str, Any] | None) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_hash(prev_hash: str, actor: str, action: str, resource: str, payload_canonical: str) -> str:
    material = f"{prev_hash}|{actor}|{action}|{resource}|{payload_canonical}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def append_audit(
    conn: asyncpg.Connection,
    *,
    actor: str,
    action: str,
    resource: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """在调用方事务内追加一条审计；链尾读取用 advisory lock 串行化。"""
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('audit_log_chain'))")
    row = await conn.fetchrow("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1")
    prev_hash = row["hash"] if row else GENESIS_HASH
    payload_canonical = canonical_payload(payload)
    row_hash = compute_hash(prev_hash, actor, action, resource, payload_canonical)
    inserted = await conn.fetchrow(
        """
        INSERT INTO audit_log (actor, action, resource, payload, prev_hash, hash)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, created_at
        """,
        actor,
        action,
        resource,
        payload_canonical,
        prev_hash,
        row_hash,
    )
    return {
        "id": inserted["id"],
        "hash": row_hash,
        "prev_hash": prev_hash,
        "created_at": inserted["created_at"].isoformat(),
    }


async def verify_chain(conn: asyncpg.Connection) -> dict[str, Any]:
    rows = await conn.fetch(
        "SELECT id, actor, action, resource, payload, prev_hash, hash FROM audit_log ORDER BY id"
    )
    previous = GENESIS_HASH
    for index, row in enumerate(rows):
        expected = compute_hash(previous, row["actor"], row["action"], row["resource"], row["payload"])
        if row["prev_hash"] != previous or row["hash"] != expected:
            return {
                "ok": False,
                "records": len(rows),
                "broken_at": row["id"],
                "broken_index": index,
                "reason": "hash_mismatch" if row["hash"] != expected else "chain_link_broken",
            }
        previous = row["hash"]
    return {"ok": True, "records": len(rows), "broken_at": None, "broken_index": None, "reason": None}

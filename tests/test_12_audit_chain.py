"""验收点 11：只追加哈希链审计 —— 链校验 + 篡改可定位到具体行。"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from app.services.audit import compute_hash
from conftest import API, create_candidate, unique_phone


async def _build_audit_rows(client, admin):
    candidate = await create_candidate(client, admin, phone=unique_phone(1))
    tokenize = await client.post(
        f"{API}/vault/tokenize",
        json={"type": "phone", "value": unique_phone(1)},
        headers=admin,
    )
    assert tokenize.status_code == 200
    detokenize = await client.post(
        f"{API}/vault/detokenize",
        json={"token": candidate["phone_token"], "reason": "审计链用例"},
        headers=admin,
    )
    assert detokenize.status_code == 200
    verify = await client.get(f"{API}/admin/audit/verify", headers=admin)
    assert verify.status_code == 200
    return candidate, verify.json()


async def test_audit_chain_is_linked_and_verifiable(client, admin, app):
    _, result = await _build_audit_rows(client, admin)
    assert result["ok"] is True
    assert result["records"] >= 3
    assert result["broken_at"] is None

    rows = await app.state.db.fetch(
        "SELECT id, actor, action, resource, payload, prev_hash, hash FROM audit_log ORDER BY id"
    )
    previous = "GENESIS"
    for row in rows:
        assert row["prev_hash"] == previous
        assert row["hash"] == compute_hash(
            previous, row["actor"], row["action"], row["resource"], row["payload"]
        )
        previous = row["hash"]


async def test_tampered_audit_row_is_located_by_id(client, admin, app):
    _, result = await _build_audit_rows(client, admin)
    assert result["ok"] is True
    rows = await app.state.db.fetch("SELECT id FROM audit_log ORDER BY id")
    target_id = rows[1]["id"]

    # 用超级用户 + session_replication_role 绕过触发器，模拟数据库被直接篡改
    async with app.state.db.connection() as conn:
        await conn.execute("SELECT set_config('session_replication_role', 'replica', false)")
        try:
            await conn.execute(
                "UPDATE audit_log SET payload = '{\"tampered\":true}' WHERE id = $1", target_id
            )
        finally:
            await conn.execute("SELECT set_config('session_replication_role', 'origin', false)")

    verify = await client.get(f"{API}/admin/audit/verify", headers=admin)
    assert verify.status_code == 200
    body = verify.json()
    assert body["ok"] is False
    assert body["broken_at"] == target_id
    assert body["reason"] == "hash_mismatch"


async def test_append_only_trigger_blocks_update_and_delete(client, admin, app):
    await _build_audit_rows(client, admin)
    row = await app.state.db.fetchrow("SELECT id FROM audit_log ORDER BY id LIMIT 1")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app.state.db.execute("UPDATE audit_log SET actor = 'hacker' WHERE id = $1", row["id"])
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app.state.db.execute("DELETE FROM audit_log WHERE id = $1", row["id"])


async def test_audit_requires_admin_role(client, admin):
    from conftest import login

    manager = await login(client, "sh_manager", "sh123456")
    response = await client.get(f"{API}/admin/audit/verify", headers=manager)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"

"""验收点 12：保留期与删除（未录用 90 天 / 对话原文 30 天 / 未成年人 24 小时）。

全部时间基于注入的冻结时钟，测试不 sleep、不等真实时间。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from conftest import (
    API,
    create_candidate,
    send_message,
    start_session,
    unique_phone,
)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def test_default_retention_deadlines_use_injected_clock(client, admin, clock):
    adult = await create_candidate(client, admin, phone=unique_phone(1))
    expected_adult = clock.now() + timedelta(days=90)
    assert abs((_parse(adult["retention_until"]) - expected_adult).total_seconds()) < 1

    minor = await create_candidate(
        client, admin, phone=unique_phone(2), birth_ym="2010-03"
    )
    expected_minor = clock.now() + timedelta(hours=24)
    assert abs((_parse(minor["retention_until"]) - expected_minor).total_seconds()) < 1


async def test_retention_run_deletes_expired_candidates_and_redacts_old_messages(
    client, admin, app, clock
):
    now = clock.now()
    db = app.state.db

    expired = await create_candidate(client, admin, phone=unique_phone(10))
    kept = await create_candidate(client, admin, phone=unique_phone(11))
    hired = await create_candidate(client, admin, phone=unique_phone(12))
    expired_minor = await create_candidate(
        client, admin, phone=unique_phone(13), birth_ym="2010-03"
    )
    kept_minor = await create_candidate(
        client, admin, phone=unique_phone(14), birth_ym="2010-03"
    )

    await db.execute(
        "UPDATE candidates SET status = 'rejected', retention_until = $2 WHERE id = $1",
        expired["id"],
        now - timedelta(days=1),
    )
    await db.execute(
        "UPDATE candidates SET status = 'rejected', retention_until = $2 WHERE id = $1",
        kept["id"],
        now + timedelta(days=1),
    )
    await db.execute(
        "UPDATE candidates SET status = 'hired', retention_until = NULL WHERE id = $1",
        hired["id"],
    )
    await db.execute(
        "UPDATE candidates SET retention_until = $2 WHERE id = $1",
        expired_minor["id"],
        now - timedelta(hours=1),
    )
    await db.execute(
        "UPDATE candidates SET retention_until = $2 WHERE id = $1",
        kept_minor["id"],
        now + timedelta(hours=23),
    )

    old_session = await start_session(client)
    await send_message(client, old_session["session_id"], "我叫王小明")
    new_session = await start_session(client)
    await send_message(client, new_session["session_id"], "我叫李四")
    await db.execute(
        "UPDATE agent_messages SET created_at = $2 WHERE session_id = $1",
        old_session["session_id"],
        now - timedelta(days=31),
    )
    await db.execute(
        "UPDATE agent_messages SET created_at = $2 WHERE session_id = $1",
        new_session["session_id"],
        now - timedelta(days=29),
    )

    response = await client.post(f"{API}/admin/retention/run", headers=admin)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["deleted_candidates"] == 2
    assert result["deleted_minors"] == 1
    assert result["redacted_messages"] == 1
    assert _parse(result["as_of"]) == now

    remaining = {
        row["id"] for row in await db.fetch("SELECT id FROM candidates")
    }
    assert str(expired["id"]) not in {str(item) for item in remaining}
    assert str(expired_minor["id"]) not in {str(item) for item in remaining}
    for survivor in (kept, hired, kept_minor):
        assert str(survivor["id"]) in {str(item) for item in remaining}

    old_message = await db.fetchrow(
        "SELECT raw_text, redacted_at FROM agent_messages WHERE session_id = $1 AND role = 'user'",
        old_session["session_id"],
    )
    assert old_message["raw_text"] is None
    assert old_message["redacted_at"] is not None
    new_message = await db.fetchrow(
        "SELECT raw_text FROM agent_messages WHERE session_id = $1 AND role = 'user'",
        new_session["session_id"],
    )
    assert new_message["raw_text"] is not None

    run_row = await db.fetchrow("SELECT * FROM retention_runs ORDER BY id DESC LIMIT 1")
    assert run_row is not None
    assert _parse(run_row["as_of"].isoformat()) == now

    verify = await client.get(f"{API}/admin/audit/verify", headers=admin)
    assert verify.json()["ok"] is True


async def test_retention_uses_injected_clock_advance_without_real_wait(client, admin, clock):
    candidate = await create_candidate(client, admin, phone=unique_phone(20))
    early = await client.post(f"{API}/admin/retention/run", headers=admin)
    assert early.json()["deleted_candidates"] == 0

    clock.advance(days=91)
    response = await client.post(f"{API}/admin/retention/run", headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()["deleted_candidates"] == 1
    assert response.json()["deleted_minors"] == 0

    gone = await client.get(f"{API}/candidates/{candidate['id']}", headers=admin)
    assert gone.status_code == 404

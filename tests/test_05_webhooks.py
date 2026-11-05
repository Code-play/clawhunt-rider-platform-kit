"""验收点 4：Webhook —— outbox + HMAC-SHA256 签名 + 指数退避重试 + 幂等去重。"""

from __future__ import annotations

import json
from datetime import datetime

from app.events import webhooks
from conftest import API, TEST_NOW, create_candidate, unique_phone

ENDPOINT = "https://hooks.example.test/rider-platform"
SECRET = "test-webhook-secret"


class RecordingTransport:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict] = []

    async def post(self, url, *, content, headers, timeout):
        self.calls.append({"url": url, "content": content, "headers": headers})
        return self.status_code, "ok" if 200 <= self.status_code < 300 else "server error"


async def _candidate_created_event(db) -> dict:
    row = await db.fetchrow(
        "SELECT * FROM outbox_events WHERE event_type = 'candidate.created' ORDER BY created_at DESC LIMIT 1"
    )
    assert row is not None, "候选人创建应写入 outbox 事件"
    return dict(row)


async def test_candidate_creation_writes_outbox_event_with_dedupe_key(client, admin, app):
    candidate = await create_candidate(client, admin, phone=unique_phone(1))
    event = await _candidate_created_event(app.state.db)
    assert event["aggregate_type"] == "candidate"
    assert str(event["aggregate_id"]) == candidate["id"]
    assert event["dedupe_key"].startswith("candidate.created:")
    assert json.loads(event["payload"])["candidate_id"] == candidate["id"]
    assert event["delivered_at"] is None


async def test_webhook_payload_is_signed_with_hmac_sha256(client, admin, app):
    await create_candidate(client, admin, phone=unique_phone(2))
    event = await _candidate_created_event(app.state.db)
    transport = RecordingTransport(200)
    result = await webhooks.deliver_event(
        app.state.db,
        event["id"],
        endpoint=ENDPOINT,
        secret=SECRET,
        transport=transport,
        now=TEST_NOW,
    )
    assert result.status == "delivered"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == ENDPOINT
    signature = call["headers"]["X-Rider-Signature"]
    assert signature.startswith("sha256=")
    assert webhooks.verify_signature(SECRET, call["content"], signature) is True
    # 篡改任何一个字节都应验签失败
    assert webhooks.verify_signature(SECRET, call["content"] + b"x", signature) is False
    assert webhooks.verify_signature("wrong-secret", call["content"], signature) is False
    # 投递记录落库
    delivery = await app.state.db.fetchrow(
        "SELECT * FROM webhook_deliveries WHERE event_id = $1", event["id"]
    )
    assert delivery["status"] == "delivered"
    assert delivery["http_status"] == 200


async def test_failed_delivery_retries_with_exponential_backoff(client, admin, app):
    await create_candidate(client, admin, phone=unique_phone(3))
    event = await _candidate_created_event(app.state.db)
    transport = RecordingTransport(500)

    first = await webhooks.deliver_event(
        app.state.db,
        event["id"],
        endpoint=ENDPOINT,
        secret=SECRET,
        transport=transport,
        now=TEST_NOW,
        backoff_base_seconds=2.0,
    )
    assert first.status == "failed"
    assert first.attempt == 1
    first_next = datetime.fromisoformat(first.next_attempt_at)
    assert (first_next - TEST_NOW).total_seconds() == 2.0

    first_retry_at = first_next
    second = await webhooks.deliver_event(
        app.state.db,
        event["id"],
        endpoint=ENDPOINT,
        secret=SECRET,
        transport=transport,
        now=first_retry_at,
        backoff_base_seconds=2.0,
    )
    assert second.status == "failed"
    assert second.attempt == 2
    second_next = datetime.fromisoformat(second.next_attempt_at)
    assert (second_next - first_retry_at).total_seconds() == 4.0

    row = await app.state.db.fetchrow("SELECT * FROM outbox_events WHERE id = $1", event["id"])
    assert row["attempts"] == 2
    assert row["last_error"] is not None


async def test_duplicate_delivery_is_idempotent_by_dedupe_key(client, admin, app):
    await create_candidate(client, admin, phone=unique_phone(4))
    event = await _candidate_created_event(app.state.db)
    transport = RecordingTransport(200)

    first = await webhooks.deliver_event(
        app.state.db, event["id"], endpoint=ENDPOINT, secret=SECRET,
        transport=transport, now=TEST_NOW,
    )
    second = await webhooks.deliver_event(
        app.state.db, event["id"], endpoint=ENDPOINT, secret=SECRET,
        transport=transport, now=TEST_NOW,
    )
    assert first.status == "delivered"
    assert second.status == "duplicate"
    assert len(transport.calls) == 1, "重复投递不应发第二次 HTTP 请求"
    count = await app.state.db.fetchval(
        "SELECT count(*) FROM webhook_deliveries WHERE event_id = $1", event["id"]
    )
    assert count == 1


async def test_status_change_emits_domain_events(client, admin, app):
    candidate = await create_candidate(client, admin, phone=unique_phone(5))
    for target in ("collecting", "complete", "booked"):
        response = await client.post(
            f"{API}/candidates/{candidate['id']}/status",
            json={"status": target},
            headers=admin,
        )
        assert response.status_code == 200, response.text
    event_types = [
        row["event_type"] for row in await app.state.db.fetch("SELECT event_type FROM outbox_events")
    ]
    assert "candidate.created" in event_types
    assert "candidate.updated" in event_types
    assert "candidate.completed" in event_types

"""Webhook 投递：HMAC-SHA256 签名、指数退避重试、(event_id, endpoint) 幂等去重。

生产由后台 worker 调 process_due_once；测试直接调 deliver_event 并注入 mock transport 与时钟。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from app.errors import ApiError


class HttpTransport(Protocol):
    async def post(
        self, url: str, *, content: bytes, headers: dict[str, str], timeout: float
    ) -> tuple[int, str]: ...


class HttpxTransport:
    def __init__(self) -> None:
        self._client: Any = None

    async def post(
        self, url: str, *, content: bytes, headers: dict[str, str], timeout: float
    ) -> tuple[int, str]:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, content=content, headers=headers)
            return response.status_code, response.text[:500]


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign_payload(secret, body), signature)


def build_body(event: dict[str, Any], attempt: int) -> bytes:
    payload = event["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    body = {
        "id": str(event["id"]),
        "type": event["event_type"],
        "aggregate_type": event["aggregate_type"],
        "aggregate_id": str(event["aggregate_id"]),
        "created_at": event["created_at"].isoformat(),
        "attempt": attempt,
        "data": payload,
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class DeliveryResult:
    event_id: str
    endpoint: str
    status: str  # delivered | failed | duplicate
    attempt: int
    http_status: int | None = None
    next_attempt_at: str | None = None
    error: str | None = None
    signature: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "endpoint": self.endpoint,
            "status": self.status,
            "attempt": self.attempt,
            "http_status": self.http_status,
            "next_attempt_at": self.next_attempt_at,
            "error": self.error,
            "signature": self.signature,
        }


async def deliver_event(
    db: Any,
    event_id: UUID | str,
    *,
    endpoint: str,
    secret: str,
    transport: HttpTransport | None = None,
    now: datetime | None = None,
    backoff_base_seconds: float = 2.0,
    max_attempts: int = 6,
    timeout: float = 5.0,
) -> DeliveryResult:
    """投递一条 outbox 事件。

    幂等：先按 (event_id, endpoint) 抢占投递行；已成功投递过则直接返回 duplicate，
    不再发第二次 HTTP 请求。
    """
    transport = transport or HttpxTransport()
    current = now or datetime.now(timezone.utc)
    event = await db.fetchrow("SELECT * FROM outbox_events WHERE id = $1", event_id)
    if event is None:
        raise ApiError(404, "event_not_found", "事件不存在")

    dedupe_key = f"{event['id']}|{endpoint}"
    claimed = await db.execute(
        """
        INSERT INTO webhook_deliveries (event_id, endpoint, dedupe_key, status, attempts)
        VALUES ($1, $2, $3, 'failed', 0)
        ON CONFLICT (dedupe_key) DO NOTHING
        """,
        event["id"],
        endpoint,
        dedupe_key,
    )
    delivery = await db.fetchrow("SELECT * FROM webhook_deliveries WHERE dedupe_key = $1", dedupe_key)

    if delivery["status"] == "delivered" or event["delivered_at"] is not None:
        return DeliveryResult(
            event_id=str(event["id"]),
            endpoint=endpoint,
            status="duplicate",
            attempt=int(delivery["attempts"]),
            http_status=delivery["http_status"],
        )

    attempt = int(event["attempts"]) + 1
    body = build_body(dict(event), attempt)
    signature = sign_payload(secret, body)
    headers = {
        "Content-Type": "application/json",
        "X-Rider-Event": event["event_type"],
        "X-Rider-Event-Id": str(event["id"]),
        "X-Rider-Delivery-Attempt": str(attempt),
        "X-Rider-Signature": signature,
    }

    http_status: int | None = None
    error: str | None = None
    try:
        http_status, response_text = await transport.post(
            endpoint, content=body, headers=headers, timeout=timeout
        )
        if not 200 <= http_status < 300:
            error = f"http_status_{http_status}: {response_text[:200]}"
    except (asyncio.TimeoutError, OSError) as exc:  # 网络异常按失败重试处理
        error = f"transport_error: {exc.__class__.__name__}"

    if error is None:
        await db.execute(
            """
            UPDATE outbox_events SET delivered_at = $2, attempts = $3, last_error = NULL
            WHERE id = $1
            """,
            event["id"],
            current,
            attempt,
        )
        await db.execute(
            """
            UPDATE webhook_deliveries
            SET status = 'delivered', http_status = $2, attempts = $3,
                delivered_at = $4, last_error = NULL
            WHERE dedupe_key = $1
            """,
            dedupe_key,
            http_status,
            attempt,
            current,
        )
        return DeliveryResult(
            event_id=str(event["id"]),
            endpoint=endpoint,
            status="delivered",
            attempt=attempt,
            http_status=http_status,
            signature=signature,
        )

    next_attempt = current + timedelta(seconds=backoff_base_seconds * (2 ** (attempt - 1)))
    exhausted = attempt >= max_attempts
    await db.execute(
        """
        UPDATE outbox_events SET attempts = $2, next_attempt_at = $3, last_error = $4
        WHERE id = $1
        """,
        event["id"],
        attempt,
        next_attempt,
        error,
    )
    await db.execute(
        """
        UPDATE webhook_deliveries
        SET status = 'failed', http_status = $2, attempts = $3, last_error = $4
        WHERE dedupe_key = $1
        """,
        dedupe_key,
        http_status,
        attempt,
        error,
    )
    return DeliveryResult(
        event_id=str(event["id"]),
        endpoint=endpoint,
        status="failed",
        attempt=attempt,
        http_status=http_status,
        next_attempt_at=next_attempt.isoformat(),
        error="max_attempts_exceeded" if exhausted else error,
        signature=signature,
    )


async def process_due_once(
    db: Any,
    *,
    endpoint: str,
    secret: str,
    transport: HttpTransport | None = None,
    now: datetime | None = None,
    limit: int = 20,
) -> list[DeliveryResult]:
    """后台 worker 的一次循环：投递所有到期未送达事件。"""
    current = now or datetime.now(timezone.utc)
    rows = await db.fetch(
        """
        SELECT id FROM outbox_events
        WHERE delivered_at IS NULL AND next_attempt_at <= $1
        ORDER BY created_at
        LIMIT $2
        """,
        current,
        limit,
    )
    results: list[DeliveryResult] = []
    for row in rows:
        results.append(
            await deliver_event(
                db,
                row["id"],
                endpoint=endpoint,
                secret=secret,
                transport=transport,
                now=current,
            )
        )
    return results

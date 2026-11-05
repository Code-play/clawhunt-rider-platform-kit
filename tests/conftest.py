"""pytest 基础设施：真实 PostgreSQL 测试库、干净 schema、合成种子、注入冻结时钟。

前置条件：`docker compose up -d db cache` 起好依赖（测试库 rider_test 会被自动创建）。
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
import pytest
import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings  # noqa: E402
from app.db import seed  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security.clock import FrozenClock  # noqa: E402

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://rider:rider_dev_password@127.0.0.1:55432/rider_test"
)
CACHE_URL = os.environ.get("CACHE_URL", "redis://127.0.0.1:56379/0")
TEST_NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)

TRUNCATE_SQL = """
TRUNCATE TABLE
    agent_messages, agent_sessions, bookings, webhook_deliveries, outbox_events,
    audit_log, vault_tokens, candidates, stations, employees, policy_docs,
    synthetic_samples, retention_runs
RESTART IDENTITY CASCADE
"""


async def _prepare_database_async(url: str) -> None:
    server_url, dbname = url.rsplit("/", 1)
    admin_url = f"{server_url}/postgres"
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()
    db = Database(url, min_size=1, max_size=2)
    await db.connect()
    try:
        await db.init_schema()
    finally:
        await db.close()


def _run_sync(coro) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    """会话级：重建 rider_test 并建好全部表/视图/触发器。"""
    _run_sync(_prepare_database_async(TEST_DATABASE_URL))
    return TEST_DATABASE_URL


@pytest_asyncio.fixture
async def settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        cache_url=CACHE_URL,
        auto_init=False,
        auto_seed=False,
        jwt_secret="test-jwt-secret",
        vault_key="test-vault-key-0123456789abcdef",
        webhook_secret="test-webhook-secret",
        webhook_backoff_base_seconds=2.0,
        llm_mode="mock",
        llm_timeout_seconds=1.0,
    )


async def _reset_and_seed(app, settings: Settings) -> None:
    async with app.state.db.transaction() as conn:
        await conn.execute(TRUNCATE_SQL)
    await seed.seed_reference(app.state.db, app.state.vault, settings, app.state.clock)


@pytest_asyncio.fixture
async def app(settings: Settings):
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        application.state.clock = FrozenClock(TEST_NOW)
        await _reset_and_seed(application, settings)
        yield application


@pytest_asyncio.fixture
async def client(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def clock(app) -> FrozenClock:
    return app.state.clock


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------
API = "/api/v1"


async def login(client: httpx.AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await client.post(f"{API}/auth/token", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    return await login(client, "admin", "admin123")


@pytest_asyncio.fixture
async def admin(client) -> dict[str, str]:
    return await login(client, "admin", "admin123")


def unique_phone(index: int) -> str:
    return f"138{index:08d}"


def unique_name(index: int) -> str:
    from app.security.anonymize import GIVEN_CHARS, SURNAMES

    return SURNAMES[index % len(SURNAMES)] + GIVEN_CHARS[index % len(GIVEN_CHARS)] + GIVEN_CHARS[
        (index * 7 + 3) % len(GIVEN_CHARS)
    ]


async def create_candidate(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    name: str = "王小明",
    phone: str = "13800138000",
    **extra,
) -> dict:
    payload = {"name": name, "phone": phone, **extra}
    response = await client.post(f"{API}/candidates", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def get_stations(client: httpx.AsyncClient, headers: dict[str, str] | None = None) -> list[dict]:
    response = await client.get(f"{API}/stations", headers=headers or {})
    assert response.status_code == 200, response.text
    body = response.json()
    return body.get("stations") or body["items"]


async def station_by_name(
    client: httpx.AsyncClient, headers: dict[str, str] | None, name: str
) -> dict:
    for station in await get_stations(client, headers):
        if station["name"] == name:
            return station
    raise AssertionError(f"station not found: {name}")


async def force_status(db: Database, candidate_id: str, status: str) -> None:
    """测试夹具：绕过状态机直接把候选人置为某状态（只用于准备前置条件）。"""
    await db.execute("UPDATE candidates SET status = $2 WHERE id = $1", candidate_id, status)


# ---------------------------------------------------------------------------
# Agent 会话辅助
# ---------------------------------------------------------------------------
AGENT = f"{API}/agent"


async def start_session(client: httpx.AsyncClient) -> dict:
    response = await client.post(f"{AGENT}/sessions")
    assert response.status_code == 201, response.text
    return response.json()


async def send_message(client: httpx.AsyncClient, session_id: str, text: str) -> dict:
    response = await client.post(f"{AGENT}/sessions/{session_id}/messages", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def missing_field_keys(progress: dict) -> list[str]:
    """progress.fields 为 [{key,label,collected}]，返回尚未收集的槽位 key。"""
    return [
        field["key"]
        for field in progress.get("fields", [])
        if isinstance(field, dict) and not field.get("collected")
    ]


def collected_field_keys(progress: dict) -> list[str]:
    return [
        field["key"]
        for field in progress.get("fields", [])
        if isinstance(field, dict) and field.get("collected")
    ]


async def fill_all_slots(client: httpx.AsyncClient) -> tuple[str, dict]:
    """走完 7 项信息收集，返回 (session_id, 最后一次响应)。"""
    session = await start_session(client)
    session_id = session["session_id"]
    replies = [
        "我叫王小明",
        "手机号 13800138000",
        "91 年 5 月出生",
        "住在杭州西湖区文三路 128 号",
        "想做全职",
        "有电动车",
        "下周一开始",
    ]
    last = session
    for text in replies:
        last = await send_message(client, session_id, text)
    return session_id, last


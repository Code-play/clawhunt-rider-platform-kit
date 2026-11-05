"""验收点 7：对话引擎 —— 7 槽位、口语抽取、未成年终止、LLM 超时降级、可插拔 mock。"""

from __future__ import annotations

import asyncio

from app.agent.llm import MockLLM
from conftest import fill_all_slots, missing_field_keys, send_message, start_session


class TimeoutLLM:
    """故障注入：模拟主模型超时。"""

    name = "openai"

    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, payload):
        self.calls += 1
        raise asyncio.TimeoutError("injected timeout")


async def test_seven_slots_are_collected_in_order_with_progress(client):
    session = await start_session(client)
    session_id = session["session_id"]
    assert session["progress"]["total"] == 7
    assert session["progress"]["done"] == 0
    assert len(session["progress"]["fields"]) == 7
    assert session["quick_replies"] == []

    script = [
        ("我叫王小明", 1),
        ("手机号 13800138000", 2),
        ("91 年 5 月出生", 3),
        ("住在杭州西湖区文三路 128 号", 4),
        ("想做全职", 5),
        ("有电动车", 6),
        ("下周一开始", 7),
    ]
    last: dict = session
    for text, expected_done in script:
        last = await send_message(client, session_id, text)
        assert last["progress"]["done"] == expected_done, (text, last)
        assert set(last["actions"]) <= {"show_stations", "booking_confirmed", "handoff", "end_minor"}

    assert last["progress"]["done"] == 7
    assert missing_field_keys(last["progress"]) == []
    assert last["actions"] == ["show_stations"]
    assert last["quick_replies"], "信息齐全后应给出可选站点"


async def test_slot_sequence_then_station_booking(client, app):
    session_id, last = await fill_all_slots(client)
    assert last["progress"]["done"] == 7
    assert missing_field_keys(last["progress"]) == []
    assert last["actions"] == ["show_stations"]
    assert "徐汇站" in last["quick_replies"]

    candidate = await app.state.db.fetchrow(
        "SELECT * FROM candidates WHERE source_channel = 'agent' ORDER BY created_at DESC LIMIT 1"
    )
    assert candidate is not None
    assert candidate["birth_ym"] == "1991-05"
    assert candidate["profile_complete"] is True
    assert candidate["status"] == "complete"

    booked = await send_message(client, session_id, "徐汇站")
    assert booked["actions"] == ["booking_confirmed"]
    assert "预约成功" in booked["reply"]

    updated = await app.state.db.fetchrow(
        "SELECT * FROM candidates WHERE id = $1", candidate["id"]
    )
    assert updated["status"] == "booked"
    bookings = await app.state.db.fetch("SELECT * FROM bookings")
    assert len(bookings) == 1
    assert bookings[0]["station_id"] == updated["station_id"]


async def test_oral_birth_ym_extraction_only_asks_year_month(client, app):
    session = await start_session(client)
    session_id = session["session_id"]
    reply = await send_message(client, session_id, "我是 91 年 5 月出生的")
    assert reply["progress"]["done"] >= 1
    assert "name" in missing_field_keys(reply["progress"])
    assert "姓名" in reply["quick_replies"] or "姓名" in reply["reply"] or "怎么称呼" in reply["reply"]


async def test_birth_ym_parsing_variants():
    from app.agent.extract import parse_birth_ym

    assert parse_birth_ym("91 年 5 月") == "1991-05"
    assert parse_birth_ym("1991-05") == "1991-05"
    assert parse_birth_ym("1991年5月出生") == "1991-05"
    assert parse_birth_ym("我是 10 年 3 月的") == "2010-03"


async def test_minor_under_18_is_terminated_politely_with_end_minor(client, app):
    session = await start_session(client)
    session_id = session["session_id"]
    await send_message(client, session_id, "我叫李小华")
    await send_message(client, session_id, "手机号 13900139000")
    reply = await send_message(client, session_id, "2010 年 3 月出生")
    assert reply["actions"] == ["end_minor"]
    assert "18" in reply["reply"]
    assert "暂" in reply["reply"] or "无法" in reply["reply"]

    minor = await app.state.db.fetchrow(
        "SELECT * FROM candidates WHERE is_minor = true ORDER BY created_at DESC LIMIT 1"
    )
    assert minor is not None
    assert minor["status"] == "rejected"
    session_row = await app.state.db.fetchrow(
        "SELECT * FROM agent_sessions WHERE id = $1", session_id
    )
    assert session_row["status"] == "terminated_minor"


async def test_user_request_handoff_marks_session_and_candidate(client, app):
    session_id, _ = await fill_all_slots(client)
    reply = await send_message(client, session_id, "我要转人工客服")
    assert reply["actions"] == ["handoff"]
    assert "人工" in reply["reply"]
    candidate = await app.state.db.fetchrow(
        "SELECT * FROM candidates WHERE source_channel = 'agent' ORDER BY created_at DESC LIMIT 1"
    )
    assert candidate["status"] == "handoff"
    session_row = await app.state.db.fetchrow(
        "SELECT * FROM agent_sessions WHERE id = $1", session_id
    )
    assert session_row["status"] == "handoff"
    event = await app.state.db.fetchrow(
        "SELECT * FROM outbox_events WHERE event_type = 'handoff.requested' ORDER BY created_at DESC LIMIT 1"
    )
    assert event is not None


async def test_llm_timeout_degrades_to_deterministic_form_mode(client, app):
    broken = TimeoutLLM()
    app.state.llm = broken
    session = await start_session(client)
    session_id = session["session_id"]
    reply = await send_message(client, session_id, "我叫王小明")
    assert broken.calls == 1
    assert reply["progress"]["mode"] == "form"
    assert "表单模式" in reply["reply"]
    assert reply["actions"] == []

    # 降级后会话保持表单模式，不再调用主模型
    second = await send_message(client, session_id, "手机号 13800138000")
    assert broken.calls == 1
    assert second["progress"]["mode"] == "form"
    assert "表单模式" in second["reply"]


async def test_mock_llm_is_deterministic_and_needs_no_key(client, app):
    llm = app.state.llm
    assert isinstance(llm, MockLLM)
    first = await start_session(client)
    second = await start_session(client)
    reply_one = await send_message(client, first["session_id"], "我叫王小明")
    reply_two = await send_message(client, second["session_id"], "我叫王小明")
    assert reply_one["reply"] == reply_two["reply"]
    assert reply_one["progress"] == reply_two["progress"]
    assert len(llm.received_payloads) == 2


def test_openai_mode_builds_openai_compatible_client_without_network():
    from app.agent.llm import OpenAICompatLLM, build_llm
    from app.config import Settings

    configured = build_llm(
        Settings(
            llm_mode="openai",
            llm_base_url="http://127.0.0.1:9/v1",
            llm_model="demo-model",
            llm_api_key="sk-test",
        )
    )
    assert isinstance(configured, OpenAICompatLLM)
    assert configured.base_url == "http://127.0.0.1:9/v1"
    assert configured.model == "demo-model"
    assert build_llm(Settings(llm_mode="mock")).name == "mock"

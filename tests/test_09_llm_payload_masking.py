"""验收点 9：送模型前脱敏 —— 模型请求体不含原始手机号/身份证，只有占位符。"""

from __future__ import annotations

import json
import random

from app.agent.llm import MockLLM
from app.security import anonymize
from conftest import send_message, start_session


async def test_llm_payload_contains_placeholders_not_raw_pii(client, app):
    llm = app.state.llm
    assert isinstance(llm, MockLLM)
    id_card = anonymize.make_id_card(random.Random(42))
    raw_name = "王小明"
    raw_phone = "13800138000"
    raw_address = "杭州西湖区文三路"

    session = await start_session(client)
    text = f"我叫{raw_name}，手机号 {raw_phone}，身份证 {id_card}，住在{raw_address} 128 号"
    await send_message(client, session["session_id"], text)

    assert llm.received_payloads, "mock LLM 应记录收到的请求体"
    payload = llm.received_payloads[-1]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert raw_phone not in serialized
    assert id_card not in serialized
    assert raw_name not in serialized
    assert raw_address not in serialized

    masked_text = payload["text"]
    assert "〔phone_1〕" in masked_text
    assert "〔id_1〕" in masked_text
    assert "〔name_1〕" in masked_text
    assert payload["placeholders"]["phone"] == ["〔phone_1〕"]
    assert payload["placeholders"]["name"] == ["〔name_1〕"]

    row = await app.state.db.fetchrow(
        "SELECT llm_payload, text_redacted, raw_text FROM agent_messages WHERE role = 'user' ORDER BY id DESC LIMIT 1"
    )
    stored_payload = json.dumps(row["llm_payload"], ensure_ascii=False)
    assert raw_phone not in stored_payload
    assert id_card not in stored_payload
    # 原文仅落 raw_text（受 30 天保留期约束），text_redacted 与模型请求体都是脱敏后的
    assert raw_phone not in row["text_redacted"]
    assert raw_phone in row["raw_text"]


async def test_masked_payload_keeps_slot_extraction_working(client, app):
    """脱敏不能破坏抽取：占位符要能被引擎映射回保险箱令牌。"""
    session = await start_session(client)
    await send_message(client, session["session_id"], "手机号 13700137000")
    candidate = await app.state.db.fetchrow(
        "SELECT * FROM candidates ORDER BY created_at DESC LIMIT 1"
    )
    assert candidate is None  # 只有手机号还不够建候选人
    session_row = await app.state.db.fetchrow(
        "SELECT context FROM agent_sessions WHERE id = $1", session["session_id"]
    )
    context = json.loads(session_row["context"])
    assert context["slots"]["phone_token"].startswith("vt_")
    assert "13700137000" not in json.dumps(context, ensure_ascii=False)

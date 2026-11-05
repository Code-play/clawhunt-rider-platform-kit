"""验收点 8：政策知识库 —— 混合检索，每条回答带出处；检索不到必须转人工。"""

from __future__ import annotations

import pytest

from conftest import send_message, start_session


async def test_policy_search_returns_citation_with_doc_name_and_version(client, admin):
    response = await client.get(
        f"/api/v1/policies/search", params={"q": "骑手年龄要求"}, headers=admin
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["handoff_required"] is False
    assert body["items"], "应检索到政策条款"
    for item in body["items"]:
        assert item["doc_name"], "每条回答必须带文档名"
        assert item["doc_version"], "每条回答必须带文档版本"
        assert item["section"]
        assert item["excerpt"]
    top = body["items"][0]
    assert top["doc_name"] == "骑手招募政策手册"
    assert top["doc_version"] == "v1.2"
    assert "18" in top["excerpt"]


async def test_policy_search_no_hit_requires_handoff_and_never_fabricates(client, admin):
    response = await client.get(
        "/api/v1/policies/search",
        params={"q": "火星基地骑手落户政策是什么"},
        headers=admin,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["handoff_required"] is True
    assert body["items"] == []
    assert "转人工" in body["message"]


async def test_agent_policy_answer_includes_citation(client):
    session = await start_session(client)
    reply = await send_message(client, session["session_id"], "骑手年龄要求是什么？")
    assert "《骑手招募政策手册》" in reply["reply"]
    assert "v1.2" in reply["reply"]
    assert reply["actions"] == []


async def test_agent_policy_no_hit_hands_off_to_human(client, app):
    session = await start_session(client)
    reply = await send_message(client, session["session_id"], "火星基地骑手落户政策是什么？")
    assert reply["actions"] == ["handoff"]
    assert "转接人工" in reply["reply"] or "转人工" in reply["reply"]
    session_row = await app.state.db.fetchrow(
        "SELECT status FROM agent_sessions WHERE id = $1", session["session_id"]
    )
    assert session_row["status"] == "handoff"


@pytest.mark.parametrize(
    ("query", "expected_doc"),
    [
        ("保险怎么算？", "骑手合作保障与商业保险说明"),
        ("结算规则是什么？", "薪酬与结算办法"),
        ("入职流程是怎样的？", "骑手到站与入职流程说明"),
        ("隐私政策怎么规定的？", "个人信息保护与保留期政策"),
    ],
)
async def test_h5_demo_policy_questions_hit_expected_doc(client, admin, query, expected_doc):
    """H5 演示按钮（保险/结算/入职/隐私）必须命中政策并带出处。"""
    response = await client.get(
        "/api/v1/policies/search", params={"q": query}, headers=admin
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["handoff_required"] is False
    doc_names = {item["doc_name"] for item in body["items"]}
    assert expected_doc in doc_names, f"{query} -> {doc_names}"
    for item in body["items"]:
        assert item["title"].startswith("《")
        assert item["effective_date"]
        assert item["disclaimer"]


async def test_policy_card_extension_in_agent_reply(client):
    session = await start_session(client)
    reply = await send_message(client, session["session_id"], "保险怎么算？")
    assert reply["policy_card"]["version"]
    assert reply["policy_card"]["title"].startswith("《")
    assert reply["policy_card"]["disclaimer"]
    assert reply["source_label"].startswith("出处：")

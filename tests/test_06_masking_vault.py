"""验收点 5：掩码与解盲 —— 列表默认掩码；detokenize 需权限 + reason + 审计。"""

from __future__ import annotations

import json

from conftest import API, create_candidate, login, unique_phone

RAW_NAME = "王小明"
RAW_PHONE = "13800138000"


async def test_candidate_list_masks_name_and_phone_by_default(client, admin):
    candidate = await create_candidate(
        client, admin, name=RAW_NAME, phone=RAW_PHONE, area_text="杭州西湖区"
    )
    assert candidate["name"] == "王**"
    assert candidate["phone"] == "138****8000"

    response = await client.get(f"{API}/candidates", headers=admin)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "王**"
    assert body["items"][0]["phone"] == "138****8000"
    assert RAW_PHONE not in response.text
    assert RAW_NAME not in response.text


async def test_detokenize_without_token_is_rejected(client):
    response = await client.post(
        f"{API}/vault/detokenize", json={"token": "vt_x", "reason": "测试"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_detokenize_requires_permission(client, admin):
    candidate = await create_candidate(client, admin, phone=RAW_PHONE)
    token = candidate["phone_token"]
    viewer = await login(client, "sh_viewer", "view123456")
    response = await client.post(
        f"{API}/vault/detokenize",
        json={"token": token, "reason": "客服核验"},
        headers=viewer,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"

    operator = await login(client, "sh_ops", "ops123456")
    response = await client.post(
        f"{API}/vault/detokenize",
        json={"token": token, "reason": "客服核验"},
        headers=operator,
    )
    assert response.status_code == 403


async def test_detokenize_requires_reason_and_writes_audit(client, admin, app):
    candidate = await create_candidate(client, admin, phone=RAW_PHONE)
    token = candidate["phone_token"]

    missing_reason = await client.post(
        f"{API}/vault/detokenize", json={"token": token, "reason": "  "}, headers=admin
    )
    assert missing_reason.status_code == 400
    assert missing_reason.json()["code"] == "reason_required"

    ok = await client.post(
        f"{API}/vault/detokenize",
        json={"token": token, "reason": "站点核验候选人身份"},
        headers=admin,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["value"] == RAW_PHONE
    assert body["reason"] == "站点核验候选人身份"

    audit_row = await app.state.db.fetchrow(
        "SELECT * FROM audit_log WHERE action = 'vault.detokenize' ORDER BY id DESC LIMIT 1"
    )
    assert audit_row is not None
    assert json.loads(audit_row["payload"])["reason"] == "站点核验候选人身份"
    assert audit_row["actor"] == "admin"

    verify = await client.get(f"{API}/admin/audit/verify", headers=admin)
    assert verify.status_code == 200
    assert verify.json()["ok"] is True


async def test_tokenize_endpoint_returns_deterministic_token(client, admin):
    first = await client.post(
        f"{API}/vault/tokenize",
        json={"type": "phone", "value": RAW_PHONE},
        headers=admin,
    )
    second = await client.post(
        f"{API}/vault/tokenize",
        json={"type": "phone", "value": RAW_PHONE},
        headers=admin,
    )
    assert first.status_code == 200
    assert first.json()["token"] == second.json()["token"]
    assert first.json()["token"].startswith("vt_")
    assert RAW_PHONE not in first.json()["token"]


async def test_duplicate_phone_is_rejected(client, admin):
    await create_candidate(client, admin, phone=unique_phone(77))
    response = await client.post(
        f"{API}/candidates",
        json={"name": "李四", "phone": unique_phone(77)},
        headers=admin,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_candidate"

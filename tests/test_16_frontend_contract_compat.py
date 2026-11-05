"""前端契约 v1 兼容层（H5 + admin）：登录别名、consent、管理端动作、H5 自助链路。

这些用例保证把 VITE_API_BASE 指向真后端时，前端不再回落 mock。
"""

from __future__ import annotations

from conftest import API, create_candidate, force_status, login, send_message, start_session

ADMIN = f"{API}/admin"


async def _consent(client, **overrides) -> dict:
    payload = {
        "consent_version": "v1.2",
        "consent_at": "2026-11-05T08:30:00+08:00",
        "source_channel": "wechat",
        **overrides,
    }
    response = await client.post(f"{API}/consent", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_cors_allows_frontend_dev_origins(client):
    """H5/admin 在 4173/4174 开发端口直连 API 时必须允许跨域。"""
    preflight = await client.options(
        f"{API}/consent",
        headers={
            "Origin": "http://127.0.0.1:4173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] in ("*", "http://127.0.0.1:4173")

    simple = await client.get(f"{API}/health", headers={"Origin": "http://127.0.0.1:4174"})
    assert simple.status_code == 200
    assert simple.headers.get("access-control-allow-origin") in ("*", "http://127.0.0.1:4174")


async def test_auth_login_alias_returns_frontend_token_and_user(client):
    response = await client.post(
        f"{API}/auth/login", json={"employee_no": "A1024", "password": "123456"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token"] and body["token_type"] == "Bearer"
    assert body["user"]["employee_no"] == "A1024"
    assert body["user"]["name"] == "张敏"
    # 前端拿 token 继续访问管理端点
    headers = {"Authorization": f"Bearer {body['token']}"}
    listing = await client.get(f"{ADMIN}/candidates", headers=headers)
    assert listing.status_code == 200


async def test_consent_creates_candidate_with_consent_fields(client):
    body = await _consent(
        client, name="王小明", phone="13800138000", source_channel="douyin"
    )
    assert body["candidate_id"]
    assert body["consent_version"] == "v1.2"
    assert body["consent_doc"]["version"] == "v1.2"

    candidate = await client.get(f"{API}/candidates/{body['candidate_id']}")
    assert candidate.status_code == 200, candidate.text
    data = candidate.json()
    assert data["name_masked"] == "王**"
    assert data["phone_masked"] == "138****8000"
    assert data["source_channel"] == "douyin"
    assert data["consent_version"] == "v1.2"
    assert data["status"] == "collecting"


async def test_h5_consent_session_fills_seven_slots_and_books_without_jwt(client, app):
    consent = await _consent(client, source_channel="wechat")
    candidate_id = consent["candidate_id"]

    session = await client.post(
        f"{API}/agent/sessions", json={"candidate_id": candidate_id}
    )
    assert session.status_code == 201, session.text
    session_body = session.json()
    assert session_body["candidate_id"] == candidate_id
    assert session_body["greeting"]["text"]
    session_id = session_body["session_id"]

    script = [
        "我叫王小明",
        "手机号 13800138000",
        "91 年 5 月出生",
        "住在杭州西湖区文三路 128 号",
        "想做全职",
        "有电动车",
        "下周一开始",
    ]
    last = session_body
    for text in script:
        last = await send_message(client, session_id, text)
    assert last["progress"]["done"] == 7
    assert last["actions"] == ["show_stations"]
    assert last["candidate_id"] == candidate_id
    assert last["stations"], "资料收齐后应推送站点推荐卡"
    assert last["stations"][0]["slots"], "站点卡需要可约时段"

    stations = await client.get(f"{API}/stations")
    assert stations.status_code == 200
    station_items = stations.json()["stations"]
    assert all("slots" in station for station in station_items)

    station = station_items[0]
    slot = next(s for s in station["slots"] if s["available"])
    booking = await client.post(
        f"{API}/bookings",
        json={
            "candidate_id": candidate_id,
            "station_id": station["id"],
            "slot_start": slot["slot_start"],
        },
    )
    assert booking.status_code == 201, booking.text
    booking_body = booking.json()
    assert booking_body["station"]["name"] == station["name"]
    assert booking_body["status"] == "booked"

    detail = await client.get(f"{API}/bookings/{booking_body['id']}")
    assert detail.status_code == 200
    assert detail.json()["station_id"] == station["id"]

    # 改约到另一个时段
    other_slot = next(
        s for s in station["slots"] if s["available"] and s["slot_start"] != slot["slot_start"]
    )
    rescheduled = await client.patch(
        f"{API}/bookings/{booking_body['id']}",
        json={"slot_start": other_slot["slot_start"]},
    )
    assert rescheduled.status_code == 200, rescheduled.text
    assert rescheduled.json()["slot_start"] == other_slot["slot_start"]

    # 自助导出（默认掩码）与撤回
    export = await client.get(f"{API}/candidates/{candidate_id}/export")
    assert export.status_code == 200, export.text
    assert export.json()["candidate"]["phone"] == "138****8000"
    assert export.json()["consent"]["version"] == "v1.2"

    revoked = await client.post(f"{API}/candidates/{candidate_id}/revoke", json={})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["deleted"] is True
    gone = await client.get(f"{API}/candidates/{candidate_id}")
    assert gone.status_code == 404
    gone_booking = await client.get(f"{API}/bookings/{booking_body['id']}")
    assert gone_booking.status_code == 404


async def test_agent_message_client_id_is_idempotent(client):
    consent = await _consent(client)
    session = await client.post(
        f"{API}/agent/sessions", json={"candidate_id": consent["candidate_id"]}
    )
    session_id = session.json()["session_id"]
    body = {"text": "我叫王小明", "client_message_id": "cmid-001"}
    first = await client.post(f"{API}/agent/sessions/{session_id}/messages", json=body)
    second = await client.post(f"{API}/agent/sessions/{session_id}/messages", json=body)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["progress"]["done"] == first.json()["progress"]["done"] == 1
    assert second.json()["message_id"] == first.json()["message_id"]


async def test_admin_actions_require_reason_and_write_audit(client, admin, app):
    candidate = await create_candidate(client, admin, phone="13900001111")
    await force_status(app.state.db, candidate["id"], "complete")
    url = f"{ADMIN}/candidates/{candidate['id']}/actions"

    no_reason = await client.post(url, json={"action": "reject"}, headers=admin)
    assert no_reason.status_code == 400
    assert no_reason.json()["code"] == "reason_required"

    no_slot = await client.post(
        url, json={"action": "confirm_interview", "reason": "候选人同意面试"}, headers=admin
    )
    assert no_slot.status_code == 400
    assert no_slot.json()["code"] == "slot_required"

    rejected = await client.post(
        url,
        json={"action": "reject", "reason": "岗位不匹配，暂不合适"},
        headers=admin,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    audit_log = rejected.json()["audit_log"]
    assert any(entry["reason"].startswith("岗位不匹配") for entry in audit_log)
    assert any(entry["to"] == "rejected" for entry in audit_log)


async def test_admin_confirm_interview_creates_booking_for_schedule(client, admin, app):
    candidate = await create_candidate(
        client, admin, phone="13900002222", station_id=None
    )
    await force_status(app.state.db, candidate["id"], "complete")
    station = (
        await client.get(f"{ADMIN}/stations", headers=admin)
    ).json()["stations"][0]
    action = await client.post(
        f"{ADMIN}/candidates/{candidate['id']}/actions",
        json={
            "action": "confirm_interview",
            "reason": "电话确认可到站面试",
            "slot_start": "2026-11-06T09:00:00+00:00",
        },
        headers=admin,
    )
    assert action.status_code == 200, action.text
    assert action.json()["status"] == "booked"

    interviews = await client.get(
        f"{ADMIN}/interviews",
        params={"from": "2026-11-05T00:00:00+00:00", "to": "2026-11-08T00:00:00+00:00"},
        headers=admin,
    )
    assert interviews.status_code == 200, interviews.text
    data = interviews.json()
    assert data["total"] >= 1
    first = data["items"][0]
    assert {"booking_id", "candidate_id", "name_masked", "station_name", "slot_start", "status"} <= set(
        first
    )


async def test_admin_list_supports_filters_and_pagination(client, admin):
    for index in range(3):
        await create_candidate(
            client, admin, name=f"王小明{index}", phone=f"1390000333{index}"
        )
    page = await client.get(
        f"{ADMIN}/candidates", params={"page": 1, "page_size": 2}, headers=admin
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1 and body["page_size"] == 2
    assert all(item["name_masked"].endswith("**") for item in body["items"])

    filtered = await client.get(
        f"{ADMIN}/candidates", params={"status": "new", "q": "13900003330"}, headers=admin
    )
    assert filtered.json()["total"] == 1


async def test_admin_metrics_and_station_quota(client, admin):
    metrics = await client.get(f"{ADMIN}/metrics", headers=admin)
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert len(body["kpis"]) == 7
    assert {kpi["key"] for kpi in body["kpis"]} >= {"new_leads", "hired", "avg_reply"}
    assert "kpi_metrics" in body

    stations = (await client.get(f"{ADMIN}/stations", headers=admin)).json()["stations"]
    target = stations[0]
    patched = await client.patch(
        f"{ADMIN}/stations/{target['id']}", json={"open_quota": 7}, headers=admin
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["open_quota"] == 7


async def test_admin_patch_requires_reason_and_maps_frontend_field_aliases(client, admin):
    candidate = await create_candidate(client, admin, phone="13900004444")
    url = f"{ADMIN}/candidates/{candidate['id']}"
    no_reason = await client.patch(
        url, json={"fields": {"area_text": "浦东新区"}}, headers=admin
    )
    assert no_reason.status_code == 400
    assert no_reason.json()["code"] == "reason_required"

    patched = await client.patch(
        url,
        json={
            "fields": {"area_text": "浦东新区", "health_cert": "yes"},
            "reason": "电话核对后补充跑单区域",
        },
        headers=admin,
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["area_text"] == "浦东新区"
    assert body["health_cert"] == "yes"
    assert any("电话核对" in entry["reason"] for entry in body["audit_log"])


async def test_detokenize_logs_listing_after_reasoned_lookup(client, admin):
    consent = await _consent(client, name="王小明", phone="13800138000")
    candidate = await client.get(f"{API}/candidates/{consent['candidate_id']}")
    token = candidate.json()["phone_token"]
    lookup = await client.post(
        f"{API}/vault/detokenize",
        json={"token": token, "reason": "站点核实候选人身份"},
        headers=admin,
    )
    assert lookup.status_code == 200, lookup.text
    logs = await client.get(f"{ADMIN}/audit/detokenize", headers=admin)
    assert logs.status_code == 200, logs.text
    assert any("核实" in log["reason"] for log in logs.json()["logs"])

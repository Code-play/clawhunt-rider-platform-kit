"""验收点 13：RBAC + 城市/站点数据域 —— 越权拒绝且不泄漏字段。"""

from __future__ import annotations

from conftest import API, create_candidate, login, station_by_name, unique_phone

RAW_NAME = "王小明"
RAW_PHONE = "13800138000"


async def test_cross_city_read_is_denied_and_leaks_no_fields(client):
    bj_manager = await login(client, "bj_manager", "bj123456")
    sh_manager = await login(client, "sh_manager", "sh123456")
    station = await station_by_name(client, bj_manager, "朝阳站")
    candidate = await create_candidate(
        client,
        bj_manager,
        name=RAW_NAME,
        phone=RAW_PHONE,
        station_id=station["id"],
    )

    denied = await client.get(f"{API}/candidates/{candidate['id']}", headers=sh_manager)
    assert denied.status_code == 404
    body = denied.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "not_found"
    assert RAW_NAME not in denied.text
    assert RAW_PHONE not in denied.text
    assert "朝" not in denied.text

    listing = await client.get(f"{API}/candidates", headers=sh_manager)
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
    assert candidate["id"] not in listing.text

    allowed = await client.get(f"{API}/candidates/{candidate['id']}", headers=bj_manager)
    assert allowed.status_code == 200
    assert allowed.json()["name"] == "王**"

    admin = await login(client, "admin", "admin123")
    assert (await client.get(f"{API}/candidates/{candidate['id']}", headers=admin)).status_code == 200


async def test_viewer_is_read_only_and_operator_station_domain(client):
    viewer = await login(client, "sh_viewer", "view123456")
    denied_create = await client.post(
        f"{API}/candidates",
        json={"name": "赵六", "phone": unique_phone(1)},
        headers=viewer,
    )
    assert denied_create.status_code == 403
    assert denied_create.json()["code"] == "forbidden"
    assert (await client.get(f"{API}/candidates", headers=viewer)).status_code == 200

    operator = await login(client, "sh_ops", "ops123456")
    xuhui = await station_by_name(client, operator, "徐汇站")
    allowed = await client.post(
        f"{API}/candidates",
        json={"name": "钱七", "phone": unique_phone(2), "station_id": xuhui["id"]},
        headers=operator,
    )
    assert allowed.status_code == 201, allowed.text

    bj_manager = await login(client, "bj_manager", "bj123456")
    chaoyang = await station_by_name(client, bj_manager, "朝阳站")
    cross_station = await client.post(
        f"{API}/candidates",
        json={"name": "孙八", "phone": unique_phone(3), "station_id": chaoyang["id"]},
        headers=operator,
    )
    assert cross_station.status_code == 403
    assert cross_station.json()["code"] == "forbidden"


async def test_unauthenticated_and_bad_token_are_rejected(client):
    no_token = await client.get(f"{API}/candidates")
    assert no_token.status_code == 401
    assert set(no_token.json()) == {"code", "message"}

    bad_token = await client.get(
        f"{API}/candidates", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert bad_token.status_code == 401
    assert bad_token.json()["code"] == "unauthorized"


async def test_kpi_and_policy_are_readable_by_viewer_but_admin_endpoint_is_not(client):
    viewer = await login(client, "sh_viewer", "view123456")
    assert (await client.get(f"{API}/kpi/summary", headers=viewer)).status_code == 200
    assert (
        await client.get(f"{API}/policies/search", params={"q": "年龄要求"}, headers=viewer)
    ).status_code == 200
    assert (await client.get(f"{API}/admin/audit/verify", headers=viewer)).status_code == 403

"""验收点 2：线索导入按 phone_token 去重 + 站点/区域/轮询分派。"""

from __future__ import annotations

from conftest import API, get_stations, unique_name, unique_phone


def _make_items(count: int) -> list[dict]:
    return [
        {
            "name": unique_name(index),
            "phone": unique_phone(index),
            "area_text": "杭州西湖区" if index % 2 else "上海徐汇区",
            "job_type": "fulltime",
        }
        for index in range(count)
    ]


async def test_import_100_leads_dedupes_by_phone_token_and_assigns_round_robin(client, admin):
    stations = await get_stations(client, admin)
    assert len(stations) >= 3
    items = _make_items(80)
    items += items[:20]  # 100 条里有 20 条重复
    assert len(items) == 100

    response = await client.post(
        f"{API}/leads/import",
        json={"items": items, "strategy": "round_robin"},
        headers=admin,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["received"] == 100
    assert body["imported"] == 80
    assert body["deduped"] == 20
    assert len(body["assignments"]) == 80

    expected_station_ids = [stations[index % len(stations)]["id"] for index in range(80)]
    assert [item["station_id"] for item in body["assignments"]] == expected_station_ids

    total = await client.get(f"{API}/candidates", params={"limit": 200}, headers=admin)
    assert total.json()["total"] == 80

    # 重复导入同样一批数据：全部按 phone_token 命中，不新增
    again = await client.post(
        f"{API}/leads/import",
        json={"items": items, "strategy": "round_robin"},
        headers=admin,
    )
    assert again.json()["imported"] == 0
    assert again.json()["deduped"] == 100


async def test_import_area_strategy_assigns_by_station_area(client, admin):
    stations = {station["name"]: station for station in await get_stations(client, admin)}
    xuhui = stations["徐汇站"]
    items = [
        {"name": unique_name(10 + index), "phone": unique_phone(10 + index), "area_text": "上海徐汇区"}
        for index in range(3)
    ]
    response = await client.post(
        f"{API}/leads/import",
        json={"items": items, "strategy": "area"},
        headers=admin,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["imported"] == 3
    assert {item["station_id"] for item in body["assignments"]} == {xuhui["id"]}


async def test_import_station_strategy_assigns_fixed_station(client, admin):
    stations = await get_stations(client, admin)
    target = stations[0]
    items = [
        {"name": unique_name(30 + index), "phone": unique_phone(30 + index)}
        for index in range(4)
    ]
    response = await client.post(
        f"{API}/leads/import",
        json={"items": items, "strategy": "station", "station_id": target["id"]},
        headers=admin,
    )
    assert response.status_code == 200, response.text
    assert {item["station_id"] for item in response.json()["assignments"]} == {target["id"]}

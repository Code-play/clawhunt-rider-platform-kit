"""验收点 3：预约不超卖 —— 50 并发抢最后 5 个名额，恰好 5 个成功且可复跑。"""

from __future__ import annotations

import asyncio

from conftest import API, create_candidate, force_status, station_by_name, unique_name, unique_phone

SLOT_START = "2026-11-06T09:00:00+00:00"


async def _prepare_candidates(client, admin, app, station, count: int = 50) -> list[dict]:
    candidates = []
    for index in range(count):
        candidate = await create_candidate(
            client,
            admin,
            name=unique_name(index),
            phone=unique_phone(index),
            station_id=station["id"],
            city="上海",
        )
        await force_status(app.state.db, candidate["id"], "complete")
        candidates.append(candidate)
    return candidates


async def _race(client, admin, candidates: list[dict], station: dict) -> list:
    async def book(candidate: dict):
        return await client.post(
            f"{API}/bookings",
            json={
                "candidate_id": candidate["id"],
                "station_id": station["id"],
                "slot_start": SLOT_START,
            },
            headers=admin,
        )

    return await asyncio.gather(*(book(candidate) for candidate in candidates))


async def test_50_concurrent_requests_race_for_last_5_slots_exactly_5_succeed(client, admin, app):
    station = await station_by_name(client, admin, "徐汇站")
    await app.state.db.execute(
        "UPDATE stations SET open_quota = 5 WHERE id = $1", station["id"]
    )
    candidates = await _prepare_candidates(client, admin, app, station)

    first_round = await _race(client, admin, candidates, station)
    statuses = [response.status_code for response in first_round]
    assert statuses.count(201) == 5, f"成功数 {statuses.count(201)} != 5"
    failures = [response for response in first_round if response.status_code != 201]
    assert len(failures) == 45
    assert all(response.status_code == 409 for response in failures)
    assert {response.json()["code"] for response in failures} == {"sold_out"}

    quota = await app.state.db.fetchval(
        "SELECT open_quota FROM stations WHERE id = $1", station["id"]
    )
    booking_count = await app.state.db.fetchval("SELECT count(*) FROM bookings")
    assert quota == 0
    assert booking_count == 5

    # 复跑稳定性：清空预约、名额恢复 5、候选人回到 complete 再抢一次，仍然恰好 5 个
    await app.state.db.execute("DELETE FROM bookings")
    await app.state.db.execute(
        "UPDATE candidates SET status = 'complete' WHERE id = ANY($1::uuid[])",
        [candidate["id"] for candidate in candidates],
    )
    await app.state.db.execute(
        "UPDATE stations SET open_quota = 5 WHERE id = $1", station["id"]
    )
    second_round = await _race(client, admin, candidates, station)
    second_statuses = [response.status_code for response in second_round]
    assert second_statuses.count(201) == 5, f"复跑成功数 {second_statuses.count(201)} != 5"
    assert (await app.state.db.fetchval("SELECT count(*) FROM bookings")) == 5
    assert (
        await app.state.db.fetchval("SELECT open_quota FROM stations WHERE id = $1", station["id"])
    ) == 0


async def test_booking_decrements_quota_atomically_and_cancel_restores(client, admin, app):
    station = await station_by_name(client, admin, "浦东站")
    candidate = await create_candidate(
        client, admin, phone=unique_phone(900), station_id=station["id"], city="上海"
    )
    await force_status(app.state.db, candidate["id"], "complete")
    before = (
        await app.state.db.fetchval("SELECT open_quota FROM stations WHERE id = $1", station["id"])
    )
    response = await client.post(
        f"{API}/bookings",
        json={"candidate_id": candidate["id"], "station_id": station["id"], "slot_start": SLOT_START},
        headers=admin,
    )
    assert response.status_code == 201, response.text
    booking = response.json()
    after = (
        await app.state.db.fetchval("SELECT open_quota FROM stations WHERE id = $1", station["id"])
    )
    assert after == before - 1

    cancel = await client.post(
        f"{API}/bookings/{booking['id']}/cancel",
        json={"reason": "候选人临时有事"},
        headers=admin,
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"
    restored = (
        await app.state.db.fetchval("SELECT open_quota FROM stations WHERE id = $1", station["id"])
    )
    assert restored == before

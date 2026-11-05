"""验收点 10：KPI —— 7 项指标由 SQL 视图单点定义，API 读数与视图完全一致。"""

from __future__ import annotations

from datetime import timedelta

from app.agent.llm import MockLLM
from conftest import API, TEST_NOW, create_candidate, unique_name, unique_phone

KPI_KEYS = {
    "leads_in",
    "ai_reception_rate",
    "profile_complete_rate",
    "ai_first_response_avg_ms",
    "ai_first_response_p95_ms",
    "booking_show_rate",
    "handoff_rate",
    "hired_count",
}


async def _seed_imported_leads(client, admin, count: int = 8) -> list[str]:
    items = [
        {"name": unique_name(index), "phone": unique_phone(index), "area_text": "上海徐汇区"}
        for index in range(count)
    ]
    response = await client.post(
        f"{API}/leads/import", json={"items": items, "strategy": "round_robin"}, headers=admin
    )
    assert response.status_code == 200, response.text
    return response.json()["candidate_ids"]


async def test_kpi_api_numbers_equal_sql_view_single_source(client, admin, app):
    candidate_ids = await _seed_imported_leads(client, admin, 8)
    db = app.state.db

    await db.execute(
        "UPDATE candidates SET status = 'hired' WHERE id = ANY($1::uuid[])", candidate_ids[:2]
    )
    await db.execute(
        "UPDATE candidates SET profile_complete = true WHERE id = ANY($1::uuid[])",
        candidate_ids[:3],
    )
    # 两个完成预约：一个到面、一个未到面
    for index, status in ((3, "done"), (4, "no_show")):
        await db.execute(
            "UPDATE candidates SET status = 'complete' WHERE id = $1", candidate_ids[index]
        )
        station = await db.fetchrow("SELECT id FROM stations ORDER BY name LIMIT 1")
        booking = await client.post(
            f"{API}/bookings",
            json={
                "candidate_id": candidate_ids[index],
                "station_id": str(station["id"]),
                "slot_start": "2026-11-06T09:00:00+00:00",
            },
            headers=admin,
        )
        assert booking.status_code == 201, booking.text
        attendance = await client.patch(
            f"{API}/bookings/{booking.json()['id']}", json={"status": status}, headers=admin
        )
        assert attendance.status_code == 200, attendance.text

    # AI 首响：两个会话分别为 250ms / 750ms
    await db.execute(
        """
        INSERT INTO agent_sessions (candidate_id, status, llm_mode, first_user_at, first_reply_at)
        VALUES ($1, 'completed', 'mock', $2, $3), ($4, 'handoff', 'mock', $2, $5)
        """,
        candidate_ids[5],
        TEST_NOW,
        TEST_NOW + timedelta(milliseconds=250),
        candidate_ids[6],
        TEST_NOW + timedelta(milliseconds=750),
    )

    response = await client.get(f"{API}/kpi/summary", headers=admin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "kpi_summary"
    metrics = body["metrics"]
    assert set(metrics) == KPI_KEYS

    view_row = await db.fetchrow("SELECT * FROM kpi_summary")
    view_metrics = {key: float(view_row[key]) for key in KPI_KEYS}
    assert metrics == view_metrics, f"API 与视图不一致: {metrics} != {view_metrics}"

    assert metrics["leads_in"] == 8.0
    assert metrics["ai_reception_rate"] == 2 / 8
    assert metrics["profile_complete_rate"] == 3 / 8
    assert metrics["ai_first_response_avg_ms"] == 500.0
    assert metrics["ai_first_response_p95_ms"] == 725.0
    assert metrics["booking_show_rate"] == 0.5
    assert metrics["handoff_rate"] == 1 / 8
    assert metrics["hired_count"] == 2.0


def test_kpi_view_definition_exists_in_schema():
    from app.config import Settings

    init_sql = Settings().init_sql_path.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW kpi_summary" in init_sql
    assert "percentile_cont(0.95)" in init_sql

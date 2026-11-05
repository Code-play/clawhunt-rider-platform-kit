"""KPI：唯一口径来自 SQL 视图 kpi_summary，API 只负责读数（同源，不二次计算）。"""

from __future__ import annotations

from typing import Any

KPI_KEYS = (
    "leads_in",
    "ai_reception_rate",
    "profile_complete_rate",
    "ai_first_response_avg_ms",
    "ai_first_response_p95_ms",
    "booking_show_rate",
    "handoff_rate",
    "hired_count",
)


async def get_kpi_summary(db: Any) -> dict[str, Any]:
    row = await db.fetchrow("SELECT * FROM kpi_summary")
    return {key: float(row[key]) for key in KPI_KEYS}

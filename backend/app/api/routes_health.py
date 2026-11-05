"""健康检查：真实探测 db 与 cache。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_cache, get_db, get_settings
from app.config import Settings
from app.db.cache import Cache
from app.db.database import Database

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(    db: Database = Depends(get_db),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    db_status = "ok"
    try:
        await db.fetchval("SELECT 1")
    except Exception:
        db_status = "down"
    cache_status = "ok" if await cache.ping() else "down"
    overall = "ok" if db_status == "ok" and cache_status == "ok" else "degraded"
    return {
        "status": overall,
        "db": db_status,
        "cache": cache_status,
        "version": "1.0.0",
        "llm_mode": settings.llm_mode,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

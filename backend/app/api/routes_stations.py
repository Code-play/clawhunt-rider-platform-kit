"""站点端点（H5 无需登录；返回距离/已约人数/可约时段）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_clock, get_db
from app.db.database import Database
from app.services import stations as station_service

router = APIRouter(prefix="/stations", tags=["stations"])


@router.get("")
async def list_stations(
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
    only_available: bool = Query(default=False),
) -> dict:
    items = await station_service.list_stations(db, clock, only_available=only_available)
    return {"stations": items, "items": items, "total": len(items)}


@router.get("/{station_id}")
async def get_station(
    station_id: str,
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
) -> dict:
    return await station_service.get_station(db, clock, station_id)

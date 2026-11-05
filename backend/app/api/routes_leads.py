"""线索批量导入端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_clock, get_db, get_settings, get_vault, require_permission
from app.config import Settings
from app.db.database import Database
from app.models.schemas import LeadImportRequest
from app.security.tokens import EmployeeContext
from app.security.vault import Vault
from app.services import leads as lead_service

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("/import")
async def import_leads(
    body: LeadImportRequest,
    employee: EmployeeContext = Depends(require_permission("candidate:write")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await lead_service.import_leads(
        db,
        vault,
        settings,
        clock,
        employee=employee,
        items=[item.model_dump() for item in body.items],
        strategy=body.strategy,
        station_id=body.station_id,
        source_channel=body.source_channel,
    )

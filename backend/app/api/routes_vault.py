"""保险箱端点：tokenize / detokenize（解盲必须带 reason、写只追加审计）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_db, get_vault, require_permission
from app.db.database import Database
from app.errors import bad_request
from app.models.schemas import VaultDetokenizeRequest, VaultTokenizeRequest
from app.security.tokens import EmployeeContext
from app.security.vault import Vault
from app.services import audit

router = APIRouter(prefix="/vault", tags=["vault"])


@router.post("/tokenize")
async def tokenize(
    body: VaultTokenizeRequest,
    employee: EmployeeContext = Depends(require_permission("candidate:write")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
) -> dict:
    async with db.transaction() as conn:
        token = await vault.tokenize(conn, body.type, body.value)
        await audit.append_audit(
            conn,
            actor=employee.username,
            action="vault.tokenize",
            resource=f"token:{token}",
            payload={"pii_type": body.type},
        )
    return {"token": token, "type": body.type}


@router.post("/detokenize")
async def detokenize(
    body: VaultDetokenizeRequest,
    employee: EmployeeContext = Depends(require_permission("vault:detokenize")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
) -> dict:
    reason = (body.reason or "").strip()
    if not reason:
        raise bad_request("reason_required", "解盲必须提供 reason（用途说明）")
    async with db.transaction() as conn:
        pii_type, value = await vault.detokenize(conn, body.token)
        audit_row = await audit.append_audit(
            conn,
            actor=employee.username,
            action="vault.detokenize",
            resource=f"token:{body.token}",
            payload={"reason": reason, "pii_type": pii_type},
        )
    return {
        "token": body.token,
        "type": pii_type,
        "value": value,
        "reason": reason,
        "audit_id": audit_row["id"],
        "field": "手机号" if pii_type == "phone" else "姓名/证件",
        "displayed_once": True,
        "note": "该值仅本次返回并展示一次，前端不缓存、不写入 localStorage。",
        "audit": audit_row,
    }

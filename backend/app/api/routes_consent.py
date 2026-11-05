"""H5 告知同意建档（契约 v1 `POST /consent`）。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_clock, get_db, get_settings, get_vault
from app.config import Settings
from app.db.database import Database
from app.errors import bad_request, not_found
from app.models.schemas import ConsentRequest
from app.security.tokens import EmployeeContext
from app.security.vault import Vault
from app.services import audit, candidates

router = APIRouter(tags=["consent"])


def _parse_consent_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise bad_request("invalid_consent_at", "consent_at 必须是 ISO 8601 时间") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@router.post("/consent")
async def save_consent(
    body: ConsentRequest,
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> dict:
    consent_at = _parse_consent_at(body.consent_at)
    actor = "candidate:self"
    if body.candidate_id:
        candidate = await candidates.get_candidate_any(db, body.candidate_id)
        now = clock.now()
        async with db.transaction() as conn:
            await conn.execute(
                """
                UPDATE candidates
                SET consent_version = $2, consent_at = $3,
                    source_channel = COALESCE($4, source_channel), updated_at = $5
                WHERE id = $1
                """,
                candidate["id"],
                body.consent_version,
                consent_at,
                body.source_channel,
                now,
            )
            await audit.append_audit(
                conn,
                actor=actor,
                action="candidate.consent",
                resource=f"candidate:{candidate['id']}",
                payload={
                    "consent_version": body.consent_version,
                    "consent_at": consent_at.isoformat(),
                    "source_channel": body.source_channel,
                },
            )
        candidate_id = str(candidate["id"])
    else:
        row = await candidates.create_candidate(
            db,
            vault,
            settings,
            clock,
            name=body.name,
            phone=body.phone,
            actor=actor,
            birth_ym=body.birth_ym,
            source_channel=body.source_channel,
            status="collecting",
            consent_version=body.consent_version,
            consent_at=consent_at,
        )
        candidate_id = str(row["id"])
    return {
        "candidate_id": candidate_id,
        "consent_version": body.consent_version,
        "consent_at": consent_at.isoformat(),
        "consent_doc": {"version": body.consent_version},
    }

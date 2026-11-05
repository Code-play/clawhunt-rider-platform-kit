"""请求模型（FastAPI 自动产出 OpenAPI）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

JobType = Literal["fulltime", "parttime", "undecided"]
HealthCert = Literal["none", "holding", "processing", "unknown"]
PiiType = Literal["phone", "id_card", "name", "address"]
AssignmentStrategy = Literal["round_robin", "area", "station"]
BIRTH_YM_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class TokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    """契约 v1 登录：工号或用户名（二选一）+ 密码。"""

    username: str | None = Field(default=None, max_length=64)
    employee_no: str | None = Field(default=None, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ConsentRequest(BaseModel):
    consent_version: str = Field(min_length=1, max_length=16)
    consent_at: str = Field(min_length=1, max_length=64)
    source_channel: str = Field(default="direct", max_length=32)
    name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    birth_ym: str | None = Field(default=None, pattern=BIRTH_YM_PATTERN)
    candidate_id: str | None = None


class AgentSessionCreate(BaseModel):
    candidate_id: str | None = None


class AgentMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    client_message_id: str | None = Field(default=None, max_length=64)


class AdminCandidatePatchRequest(BaseModel):
    fields: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=256)


class AdminCandidateActionRequest(BaseModel):
    action: Literal["confirm_interview", "handoff", "reject", "update_fields"]
    reason: str = Field(default="", max_length=256)
    slot_start: datetime | None = None
    fields: dict[str, object] = Field(default_factory=dict)


class StationQuotaPatch(BaseModel):
    open_quota: int = Field(ge=0, le=99)


class CandidateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=6, max_length=32)
    birth_ym: str | None = Field(default=None, pattern=BIRTH_YM_PATTERN)
    area_text: str | None = Field(default=None, max_length=128)
    job_type: JobType | None = None
    has_ebike: bool | None = None
    start_text: str | None = Field(default=None, max_length=64)
    experience_text: str | None = Field(default=None, max_length=256)
    health_cert: HealthCert | None = None
    source_channel: str = Field(default="manual", max_length=32)
    station_id: str | None = None
    city: str | None = Field(default=None, max_length=32)
    consent_version: str = Field(default="v1", max_length=16)


class CandidatePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    birth_ym: str | None = Field(default=None, pattern=BIRTH_YM_PATTERN)
    area_text: str | None = Field(default=None, max_length=128)
    job_type: JobType | None = None
    has_ebike: bool | None = None
    start_text: str | None = Field(default=None, max_length=64)
    experience_text: str | None = Field(default=None, max_length=256)
    health_cert: HealthCert | None = None
    station_id: str | None = None
    city: str | None = Field(default=None, max_length=32)


class StatusUpdate(BaseModel):
    status: str


class LeadItem(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=6, max_length=32)
    birth_ym: str | None = Field(default=None, pattern=BIRTH_YM_PATTERN)
    area_text: str | None = Field(default=None, max_length=128)
    job_type: JobType | None = None
    has_ebike: bool | None = None
    start_text: str | None = Field(default=None, max_length=64)
    health_cert: HealthCert | None = None
    source_channel: str | None = Field(default=None, max_length=32)


class LeadImportRequest(BaseModel):
    items: list[LeadItem]
    strategy: AssignmentStrategy = "round_robin"
    station_id: str | None = None
    source_channel: str = Field(default="import", max_length=32)


class BookingCreate(BaseModel):
    candidate_id: str
    station_id: str
    slot_start: datetime


class BookingAttendanceUpdate(BaseModel):
    status: Literal["done", "no_show"]


class BookingCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=256)


class BookingPatchRequest(BaseModel):
    slot_start: datetime | None = None
    status: Literal["done", "no_show"] | None = None


class RevokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=256)


class VaultTokenizeRequest(BaseModel):
    type: PiiType
    value: str = Field(min_length=1, max_length=128)


class VaultDetokenizeRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=256)


class OutboxDeliverRequest(BaseModel):
    endpoint: str | None = None

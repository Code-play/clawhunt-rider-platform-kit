"""FastAPI 依赖：数据库/缓存/时钟/保险箱/LLM 与认证、RBAC 依赖。"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agent.llm import LLMClient
from app.config import Settings
from app.db.cache import Cache
from app.db.database import Database
from app.errors import forbidden, unauthorized
from app.security.tokens import EmployeeContext, decode_access_token
from app.security.vault import Vault

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


def get_clock(request: Request) -> object:
    return request.app.state.clock


def get_vault(request: Request) -> Vault:
    return request.app.state.vault


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm


async def current_employee(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
) -> EmployeeContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized("缺少 Bearer 令牌")
    try:
        payload = decode_access_token(credentials.credentials, secret=settings.jwt_secret)
    except Exception as exc:
        raise unauthorized("令牌无效或已过期") from exc
    row = await db.fetchrow(
        "SELECT id, username, role, city, station_ids FROM employees WHERE id = $1",
        payload.get("sub"),
    )
    if row is None:
        raise unauthorized("员工不存在")
    return EmployeeContext(
        id=str(row["id"]),
        username=row["username"],
        role=row["role"],
        city=row["city"],
        station_ids=tuple(str(item) for item in row["station_ids"]),
    )


async def optional_employee(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
) -> EmployeeContext | None:
    """H5 与员工端共用的端点：无令牌按「求职者自助（capability=候选人 id）」处理；
    带了令牌但无效则按未认证拒绝（不静默降级）。"""
    if credentials is None:
        return None
    return await current_employee(request, credentials, settings, db)


def require_permission(permission: str):
    async def dependency(employee: EmployeeContext = Depends(current_employee)) -> EmployeeContext:
        if not employee.has(permission):
            raise forbidden(f"当前角色 {employee.role} 缺少权限 {permission}")
        return employee

    return dependency


def require_roles(*roles: str):
    async def dependency(employee: EmployeeContext = Depends(current_employee)) -> EmployeeContext:
        if employee.role not in roles:
            raise forbidden(f"当前角色 {employee.role} 无权访问该端点")
        return employee

    return dependency

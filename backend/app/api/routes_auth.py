"""员工登录：用户名/密码 -> Bearer JWT；同时提供契约 v1 别名 `/auth/login`。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_db, get_settings
from app.config import Settings
from app.db.database import Database
from app.errors import unauthorized
from app.models.schemas import LoginRequest, TokenRequest
from app.security.tokens import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


async def _find_employee(db: Database, identifier: str):
    return await db.fetchrow(
        "SELECT * FROM employees WHERE username = $1 OR display_name = $1", identifier
    )


def _issue(row, settings: Settings) -> str:
    return create_access_token(
        secret=settings.jwt_secret,
        employee_id=str(row["id"]),
        username=row["username"],
        role=row["role"],
        city=row["city"],
        station_ids=[str(item) for item in row["station_ids"]],
        ttl_seconds=settings.jwt_ttl_seconds,
    )


@router.post("/token")
async def issue_token(
    body: TokenRequest,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    row = await _find_employee(db, body.username)
    if row is None or not verify_password(body.password, row["salt"], row["password_hash"]):
        raise unauthorized("用户名或密码错误")
    return {
        "access_token": _issue(row, settings),
        "token_type": "bearer",
        "expires_in": settings.jwt_ttl_seconds,
        "employee": {
            "id": str(row["id"]),
            "username": row["username"],
            "role": row["role"],
            "city": row["city"],
            "station_ids": [str(item) for item in row["station_ids"]],
            "display_name": row["display_name"],
        },
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """契约 v1 登录别名：`{employee_no|username, password}` → `{token, user}`。"""
    identifier = (body.employee_no or body.username or "").strip()
    if not identifier:
        raise unauthorized("请输入工号与密码")
    row = await _find_employee(db, identifier)
    if row is None or not verify_password(body.password, row["salt"], row["password_hash"]):
        raise unauthorized("工号或密码错误")
    token = _issue(row, settings)
    return {
        "token": token,
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": settings.jwt_ttl_seconds,
        "user": {
            "name": row["display_name"],
            "employee_no": row["username"],
            "username": row["username"],
            "role": row["role"],
            "city": row["city"],
            "station": None,
        },
        "employee": {
            "id": str(row["id"]),
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "city": row["city"],
            "station_ids": [str(item) for item in row["station_ids"]],
        },
    }

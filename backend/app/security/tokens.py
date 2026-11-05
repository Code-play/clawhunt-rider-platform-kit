"""JWT 签发/校验 + 角色权限矩阵（RBAC）。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "city_manager": {
        "candidate:read",
        "candidate:write",
        "booking:write",
        "vault:detokenize",
        "kpi:read",
        "policy:read",
    },
    "station_operator": {
        "candidate:read",
        "candidate:write",
        "booking:write",
        "kpi:read",
        "policy:read",
    },
    "viewer": {"candidate:read", "kpi:read", "policy:read"},
}

ROLES = tuple(ROLE_PERMISSIONS)


@dataclass(frozen=True)
class EmployeeContext:
    id: str
    username: str
    role: str
    city: str
    station_ids: tuple[str, ...]

    def has(self, permission: str) -> bool:
        perms = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in perms or permission in perms

    def can_access_city(self, city: str) -> bool:
        return self.city == "*" or self.city == city

    def can_access_station(self, station_id: str | None) -> bool:
        if self.role != "station_operator":
            return True
        if station_id is None:
            return False
        return station_id in self.station_ids


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()


def make_salt() -> str:
    return secrets.token_hex(8)


def create_access_token(
    *,
    secret: str,
    employee_id: str,
    username: str,
    role: str,
    city: str,
    station_ids: list[str] | tuple[str, ...],
    ttl_seconds: int,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(timezone.utc)
    payload = {
        "sub": employee_id,
        "username": username,
        "role": role,
        "city": city,
        "stations": list(station_ids),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, *, secret: str) -> dict[str, object]:
    return jwt.decode(token, secret, algorithms=["HS256"])


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected_hash)

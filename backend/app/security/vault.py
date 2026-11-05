"""保险箱：确定性令牌（HMAC）+ Fernet 密文存储；解盲必须带 reason 并写审计。"""

from __future__ import annotations

import base64
import hashlib
import hmac

import asyncpg
from cryptography.fernet import Fernet, InvalidToken

from app.errors import ApiError

ALLOWED_TYPES = {"phone", "id_card", "name", "address"}


def _fernet_from_key(key: str) -> Fernet:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class Vault:
    """type + value -> 确定性 token；同一值永远同一 token（用于去重）。"""

    def __init__(self, key: str) -> None:
        self._key = key.encode("utf-8")
        self._fernet = _fernet_from_key(key)

    def token_for(self, pii_type: str, value: str) -> str:
        if pii_type not in ALLOWED_TYPES:
            raise ApiError(422, "invalid_type", f"不支持的令牌类型: {pii_type}")
        normalized = value.strip()
        mac = hmac.new(self._key, f"{pii_type}:{normalized}".encode("utf-8"), hashlib.sha256).hexdigest()
        return f"vt_{mac[:32]}"

    async def tokenize(self, conn: asyncpg.Connection, pii_type: str, value: str) -> str:
        token = self.token_for(pii_type, value)
        ciphertext = self._fernet.encrypt(value.strip().encode("utf-8")).decode("ascii")
        await conn.execute(
            """
            INSERT INTO vault_tokens (token, pii_type, ciphertext)
            VALUES ($1, $2, $3)
            ON CONFLICT (token) DO NOTHING
            """,
            token,
            pii_type,
            ciphertext,
        )
        return token

    async def detokenize(self, conn: asyncpg.Connection, token: str) -> tuple[str, str]:
        row = await conn.fetchrow(
            "SELECT pii_type, ciphertext FROM vault_tokens WHERE token = $1", token
        )
        if row is None:
            raise ApiError(404, "token_not_found", "令牌不存在")
        try:
            value = self._fernet.decrypt(row["ciphertext"].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:  # pragma: no cover - 密钥轮换场景
            raise ApiError(500, "vault_decrypt_failed", "令牌解密失败") from exc
        return row["pii_type"], value

    async def fetch_ciphertexts(self, db: object, tokens: list[str]) -> dict[str, str]:
        """批量取密文（列表页掩码用，避免 N+1 查询）。"""
        if not tokens:
            return {}
        rows = await db.fetch(  # type: ignore[attr-defined]
            "SELECT token, ciphertext FROM vault_tokens WHERE token = ANY($1::text[])", tokens
        )
        return {row["token"]: row["ciphertext"] for row in rows}

    def decrypt_ciphertext(self, ciphertext: str | None) -> str | None:
        if not ciphertext:
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return None

    async def detokenize_value(self, db: object, token: str | None) -> str:
        """内部按令牌取明文（导出副本等已鉴权场景）。"""
        if not token:
            return ""
        row = await db.fetchrow(  # type: ignore[attr-defined]
            "SELECT ciphertext FROM vault_tokens WHERE token = $1", token
        )
        if row is None:
            return ""
        return self.decrypt_ciphertext(row["ciphertext"]) or ""

    async def reveal_masked(self, conn: asyncpg.Connection, token: str, pii_type: str) -> str:
        """内部展示用：解密后按类型掩码，绝不返回明文。"""
        from app.security.masking import mask_name, mask_phone

        found_type, value = await self.detokenize(conn, token)
        if found_type != pii_type:  # pragma: no cover - 数据一致性
            return "***"
        if pii_type == "phone":
            return mask_phone(value)
        if pii_type == "name":
            return mask_name(value)
        return "***"

"""asyncpg 连接池 + schema 初始化。"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

_DOLLAR_BLOCK = re.compile(r"\$\$.*?\$\$", re.S)


def split_sql_statements(sql: str) -> list[str]:
    """按分号切分 SQL，跳过 plpgsql 的 $$...$$ 块与注释。"""
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(sql):
        dollar = _DOLLAR_BLOCK.match(sql, i)
        if dollar:
            buf.append(dollar.group(0))
            i = dollar.end()
            continue
        ch = sql[i]
        if ch == "-" and sql.startswith("--", i):
            line_end = sql.find("\n", i)
            i = len(sql) if line_end == -1 else line_end + 1
            continue
        if ch == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


class Database:
    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 20) -> None:
        self.url = url
        self.min_size = min_size
        self.max_size = max_size
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                dsn=self.url, min_size=self.min_size, max_size=self.max_size
            )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def require_pool(self) -> asyncpg.Pool:
        if self.pool is None:  # pragma: no cover - 生命周期错误
            raise RuntimeError("database pool is not connected")
        return self.pool

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        pool = self.require_pool()
        async with pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        pool = self.require_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def execute(self, query: str, *args: object) -> str:
        pool = self.require_pool()
        return await pool.execute(query, *args)

    async def fetch(self, query: str, *args: object) -> list[asyncpg.Record]:
        pool = self.require_pool()
        return await pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        pool = self.require_pool()
        return await pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: object) -> object:
        pool = self.require_pool()
        return await pool.fetchval(query, *args)

    async def init_schema(self, path: Path | str | None = None) -> None:
        """幂等建表：容器首启与 API 启动都会执行。"""
        sql_path = Path(path) if path else self._default_init_sql()
        sql = sql_path.read_text(encoding="utf-8")
        async with self.connection() as conn:
            for statement in split_sql_statements(sql):
                await conn.execute(statement)
        logger.info("schema initialized from %s", sql_path)

    @staticmethod
    def _default_init_sql() -> Path:
        return Path(__file__).resolve().parent / "init.sql"

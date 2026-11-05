"""Valkey/Redis 缓存客户端（仅健康检查与后续扩展用）。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Cache:
    def __init__(self, url: str) -> None:
        self.url = url
        self.client: Any = None

    async def connect(self) -> None:
        try:
            from redis.asyncio import from_url

            self.client = from_url(self.url, decode_responses=True)
            await self.client.ping()
        except Exception as exc:  # 缓存不可用不应阻塞 API 启动
            logger.warning("cache unavailable: %s", exc)
            self.client = None

    async def close(self) -> None:
        if self.client is not None:
            try:
                await self.client.aclose()
            except Exception:  # pragma: no cover
                pass
            self.client = None

    async def ping(self) -> bool:
        if self.client is None:
            return False
        try:
            return bool(await self.client.ping())
        except Exception:
            return False

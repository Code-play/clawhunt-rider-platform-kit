"""应用入口：create_app() 供 uvicorn / 测试使用。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.llm import build_llm
from app.api.router import api_router
from app.config import Settings, get_settings
from app.db import seed
from app.db.cache import Cache
from app.db.database import Database
from app.errors import install_error_handlers
from app.security.clock import SystemClock
from app.security.vault import Vault

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db: Database = app.state.db
        await db.connect()
        if app.state.settings.auto_init:
            await db.init_schema()
            logger.info("database schema ready")
        if app.state.settings.auto_seed:
            await seed.seed_if_empty(db, app.state.vault, app.state.settings, app.state.clock)
            logger.info("seed data ready")
        await app.state.cache.connect()
        try:
            yield
        finally:
            await app.state.cache.close()
            await db.close()

    app = FastAPI(
        title="骑手招聘 Agent 化信息收集平台 API（契约 v1）",
        description=(
            "投标用可运行公共骨架 + 垂直切片：候选人状态机、线索去重、预约防超卖、"
            "outbox/Webhook 签名、保险箱掩码、脱敏、Agent 对话、政策知识库、KPI 视图、"
            "哈希链审计、保留期删除、RBAC 数据域。仅使用合成/脱敏数据。"
        ),
        version="1.0.0",
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = Database(
        settings.database_url, min_size=settings.db_pool_min, max_size=settings.db_pool_max
    )
    app.state.cache = Cache(settings.cache_url)
    app.state.clock = SystemClock()
    app.state.vault = Vault(settings.vault_key)
    app.state.llm = build_llm(settings)

    install_error_handlers(app)
    # H5/admin 开发服务器（4173/4174 等）跨端口访问本 API 需要 CORS
    cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()

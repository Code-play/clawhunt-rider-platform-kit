"""路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    routes_admin,
    routes_agent,
    routes_auth,
    routes_bookings,
    routes_candidates,
    routes_compat,
    routes_consent,
    routes_health,
    routes_kpi,
    routes_leads,
    routes_policies,
    routes_stations,
    routes_vault,
)

api_router = APIRouter()
api_router.include_router(routes_health.router)
api_router.include_router(routes_auth.router)
api_router.include_router(routes_consent.router)
api_router.include_router(routes_candidates.router)
api_router.include_router(routes_leads.router)
api_router.include_router(routes_stations.router)
api_router.include_router(routes_bookings.router)
api_router.include_router(routes_vault.router)
api_router.include_router(routes_agent.router)
api_router.include_router(routes_policies.router)
api_router.include_router(routes_kpi.router)
api_router.include_router(routes_compat.router)
api_router.include_router(routes_admin.router)

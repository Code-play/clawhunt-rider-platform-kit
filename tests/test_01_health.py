"""验收点 14：健康检查 + OpenAPI 文档可用。"""

from __future__ import annotations

API = "/api/v1"


async def test_health_returns_db_and_cache_status(client):
    response = await client.get(f"{API}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["cache"] == "ok"
    assert body["version"] == "1.0.0"


async def test_openapi_document_is_served(client):
    response = await client.get(f"{API}/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.")
    expected_paths = {
        f"{API}/health",
        f"{API}/candidates",
        f"{API}/bookings",
        f"{API}/vault/detokenize",
        f"{API}/agent/sessions",
        f"{API}/kpi/summary",
        f"{API}/policies/search",
    }
    assert expected_paths.issubset(set(spec["paths"]))
    docs = await client.get(f"{API}/docs")
    assert docs.status_code == 200


async def test_error_body_is_code_message(client):
    # 员工专属端点不带令牌 -> 401，错误体仍是 {code, message}
    response = await client.get(f"{API}/candidates")
    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "unauthorized"

    # 非法 id -> 404，而不是 500
    missing = await client.get(f"{API}/candidates/does-not-exist")
    assert missing.status_code == 404
    assert set(missing.json()) == {"code", "message"}
    assert missing.json()["code"] == "not_found"

    unknown_route = await client.get(f"{API}/nope/not-a-route")
    assert unknown_route.status_code == 404
    assert set(unknown_route.json()) == {"code", "message"}
    assert unknown_route.json()["code"] == "not_found"

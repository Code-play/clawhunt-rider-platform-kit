"""依赖许可白名单：只允许 MIT / Apache-2.0 / BSD / PostgreSQL，禁止 GPL / AGPL。"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"

ALLOWED_LICENSES = {
    "MIT",
    "Apache-2.0",
    "BSD-3-Clause",
    "BSD-2-Clause",
    "PostgreSQL",
    "Apache-2.0 OR BSD-3-Clause",
}

KNOWN_LICENSES = {
    "fastapi": "MIT",
    "uvicorn": "BSD-3-Clause",
    "asyncpg": "Apache-2.0",
    "redis": "MIT",
    "pyjwt": "MIT",
    "cryptography": "Apache-2.0 OR BSD-3-Clause",
    "httpx": "BSD-3-Clause",
    "pydantic": "MIT",
    "pydantic-settings": "MIT",
    "pytest": "MIT",
    "pytest-asyncio": "Apache-2.0",
}


def _parse_requirements() -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        package, _, version = line.partition("==")
        name = package.strip().split("[")[0].strip().lower()
        entries[name] = version.strip()
    return entries


def test_runtime_dependencies_are_version_pinned_and_permissively_licensed():
    entries = _parse_requirements()
    assert entries, "requirements.txt 不应为空"
    for name, version in entries.items():
        assert version, f"{name} 未钉住版本"
        license_name = KNOWN_LICENSES.get(name)
        assert license_name is not None, f"{name} 未登记许可，需人工审计"
        assert license_name in ALLOWED_LICENSES, f"{name} 许可 {license_name} 不在白名单"


def test_no_copyleft_dependency_is_declared():
    entries = _parse_requirements()
    for name in entries:
        assert "gpl" not in name, f"禁止 GPL/AGPL 依赖: {name}"
    for forbidden in ("gpl", "agpl"):
        for name in entries:
            assert forbidden not in name

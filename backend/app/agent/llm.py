"""可插拔 LLM：

- LLM_MODE=mock：确定性本地规则引擎（不联网、不需要密钥），测试与干净机器默认使用；
- LLM_MODE=openai：OpenAI 兼容 /chat/completions 接口（base_url / model 可配）；
  超时或网络错误会抛出 LLMUnavailable，由对话引擎降级为表单式问答。

送进 LLM 的 payload 必须已经过脱敏（见 agent.engine），mock 会记录收到的 payload 供测试断言。
"""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.agent.extract import extract_slots

SYSTEM_PROMPT = (
    "你是骑手招聘信息收集助手。只从用户消息中抽取槽位，输出 JSON："
    '{"slots": {"name": ..., "phone": ..., "birth_ym": "YYYY-MM", "area_text": ..., '
    '"job_type": "fulltime|parttime|undecided", "has_ebike": true|false, "start_text": ...}}。'
    "消息里的〔phone_1〕〔name_1〕〔addr_1〕是脱敏占位符，遇到时原样填入对应槽位，不要猜测内容。"
)


class LLMUnavailable(Exception):
    """LLM 超时/网络错误/返回非法 JSON —— 触发表单降级。"""


@dataclass
class LLMResult:
    slots: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    name: str

    async def extract(self, payload: dict[str, Any]) -> LLMResult: ...


class MockLLM:
    """确定性本地实现：不联网、不依赖密钥；记录收到的请求体（已脱敏）。"""

    name = "mock"

    def __init__(self) -> None:
        self.received_payloads: list[dict[str, Any]] = []

    async def extract(self, payload: dict[str, Any]) -> LLMResult:
        self.received_payloads.append(copy.deepcopy(payload))
        text = str(payload.get("text", ""))
        slots = extract_slots(text)
        # 脱敏占位符原样回填，交给对话引擎映射成保险箱令牌
        for slot in ("name", "phone", "area_text"):
            for placeholder in payload.get("placeholders", {}).get(slot, []):
                if placeholder in text:
                    slots[slot] = placeholder
                    break
        return LLMResult(slots=slots, raw={"mode": "mock"})


class OpenAICompatLLM:
    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float,
    ) -> None:
        if not base_url:
            raise ValueError("LLM_MODE=openai 时必须配置 LLM_BASE_URL")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def extract(self, payload: dict[str, Any]) -> LLMResult:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=body, headers=headers
                )
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            slots = parsed.get("slots", {}) if isinstance(parsed, dict) else {}
            return LLMResult(slots=slots if isinstance(slots, dict) else {}, raw=data)
        except (httpx.HTTPError, asyncio.TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(str(exc)) from exc


def build_llm(settings: Any) -> LLMClient:
    if settings.llm_mode == "openai":
        return OpenAICompatLLM(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return MockLLM()

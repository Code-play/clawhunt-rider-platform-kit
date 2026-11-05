"""可注入时钟：保留期等时间敏感逻辑一律走 Clock，测试可冻结/回拨。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:  # pragma: no cover - protocol
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass
class FrozenClock:
    """测试用时钟：固定时刻，可手动推进。"""

    fixed: datetime
    _shift: timedelta = field(default=timedelta(0))

    def now(self) -> datetime:
        return self.fixed + self._shift

    def advance(self, **kwargs: float) -> None:
        self._shift += timedelta(**kwargs)

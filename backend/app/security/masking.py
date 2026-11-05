"""展示用掩码：手机号 138****8000，姓名 王**（姓名只露首字）。"""

from __future__ import annotations


def mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}****{digits[-4:]}"


def mask_name(name: str) -> str:
    if not name:
        return "**"
    return name[0] + "*" * max(2, len(name) - 1)

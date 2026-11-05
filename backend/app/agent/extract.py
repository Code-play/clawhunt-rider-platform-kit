"""槽位定义 + 确定性口语抽取（mock LLM 与表单降级共用）。"""

from __future__ import annotations

import re

SLOTS: tuple[str, ...] = (
    "name",
    "phone",
    "birth_ym",
    "area_text",
    "job_type",
    "has_ebike",
    "start_text",
)
SLOT_TOTAL = len(SLOTS)

SLOT_LABELS = {
    "name": "姓名",
    "phone": "手机号",
    "birth_ym": "出生年月",
    "area_text": "所在区域",
    "job_type": "工作类型",
    "has_ebike": "电动车情况",
    "start_text": "可到岗时间",
}

SLOT_EXAMPLES = {
    "name": "王小明",
    "phone": "13800138000",
    "birth_ym": "91 年 5 月",
    "area_text": "杭州西湖区",
    "job_type": "全职",
    "has_ebike": "有",
    "start_text": "下周一",
}

SLOT_QUESTIONS = {
    "name": "请问怎么称呼你？",
    "phone": "请留下手机号，方便站点联系你。",
    "birth_ym": "请告诉我你的出生年月（例如：91 年 5 月，只问年月）。",
    "area_text": "你现在住哪个区域？例如：杭州西湖区。",
    "job_type": "你想做全职还是兼职？",
    "has_ebike": "你有自己的电动车吗？",
    "start_text": "你最快什么时候能开始上班？",
}

SLOT_QUICK_REPLIES: dict[str, list[str]] = {
    "name": [],
    "phone": [],
    "birth_ym": ["1990 年 5 月", "1995 年 8 月", "暂时不方便说"],
    "area_text": ["浦东新区", "徐汇区", "朝阳区"],
    "job_type": ["全职", "兼职", "还没定"],
    "has_ebike": ["有", "没有"],
    "start_text": ["明天", "下周", "随时"],
}

_POLICY_KEYWORDS = ("?", "？", "政策", "规定", "要求", "怎么办", "流程", "多久", "多少", "能不能", "可以吗", "工资", "结算")
_HANDOFF_KEYWORDS = ("人工", "转人工", "客服", "投诉", "电话联系", "找真人")

_YEAR_MONTH_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})\s*[-/.年]\s*(\d{1,2})(?!\d)")
_SHORT_YEAR_RE = re.compile(r"(?<!\d)(\d{2})\s*年\s*(\d{1,2})\s*月?")
_MONTH_ONLY_RE = re.compile(r"(?<!\d)(\d{1,2})\s*月(?:份)?(?:出生|生)?")

_JOB_TYPE_PATTERNS = (
    (("全职", "正式", "长期", "固定班"), "fulltime"),
    (("兼职", "临时", "小时工", "周末做"), "parttime"),
    (("还没定", "不确定", "都行", "都可以", "随便", "考虑中"), "undecided"),
)

_START_RE = re.compile(
    r"(下周[一二三四五六日天]?|下个?月|月底|月初|明天|后天|今天|随时|马上|立刻|一周内|一个月后|(?<!\d)\d{1,2}\s*号(?:开始|到岗|上班))"
)
_AREA_RE = re.compile(r"(?:住在|现住|在|位置在|工作地点在)\s*([\u4e00-\u9fa5]{2,10}(?:区|县|镇|街道|村))")


def parse_birth_ym(text: str) -> str | None:
    """「91 年 5 月」-> 1991-05；「2010-03」-> 2010-03。"""
    match = _YEAR_MONTH_RE.search(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
    match = _SHORT_YEAR_RE.search(text)
    if match:
        short_year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            return None
        full_year = 2000 + short_year if short_year <= 30 else 1900 + short_year
        return f"{full_year:04d}-{month:02d}"
    return None


def extract_job_type(text: str) -> str | None:
    for keywords, value in _JOB_TYPE_PATTERNS:
        if any(keyword in text for keyword in keywords):
            return value
    return None


def extract_has_ebike(text: str) -> bool | None:
    if re.search(r"(没有|没|无|不骑)[^，。,.!?！？]{0,4}(电动车|电瓶车|车)", text):
        return False
    if re.search(r"(有|自带|骑着|自备)[^，。,.!?！？]{0,3}(电动车|电瓶车|车)", text):
        return True
    return None


def extract_start_text(text: str) -> str | None:
    match = _START_RE.search(text)
    return match.group(1) if match else None


def extract_area_text(text: str) -> str | None:
    match = _AREA_RE.search(text)
    return match.group(1) if match else None


def extract_slots(text: str) -> dict[str, object]:
    """从（已脱敏的）文本里抽取非 PII 槽位；PII 槽位由调用方另走保险箱。"""
    slots: dict[str, object] = {}
    birth_ym = parse_birth_ym(text)
    if birth_ym:
        slots["birth_ym"] = birth_ym
    job_type = extract_job_type(text)
    if job_type:
        slots["job_type"] = job_type
    has_ebike = extract_has_ebike(text)
    if has_ebike is not None:
        slots["has_ebike"] = has_ebike
    start_text = extract_start_text(text)
    if start_text:
        slots["start_text"] = start_text
    area_text = extract_area_text(text)
    if area_text:
        slots["area_text"] = area_text
    return slots


def is_policy_question(text: str) -> bool:
    return any(keyword in text for keyword in _POLICY_KEYWORDS)


def wants_handoff(text: str) -> bool:
    return any(keyword in text for keyword in _HANDOFF_KEYWORDS)


def next_missing_slot(slots: dict[str, object]) -> str | None:
    for slot in SLOTS:
        if slot not in slots or slots[slot] in (None, ""):
            return slot
    return None


def question_for(slot: str, index: int) -> tuple[str, list[str]]:
    prompt = SLOT_QUESTIONS[slot]
    return f"（第 {index + 1}/{SLOT_TOTAL} 项）{prompt}", list(SLOT_QUICK_REPLIES[slot])


def form_question_for(slot: str, index: int) -> str:
    return (
        f"【表单模式】主模型暂不可用，请按表单填写第 {index + 1}/{SLOT_TOTAL} 项"
        f"「{SLOT_LABELS[slot]}」（示例：{SLOT_EXAMPLES[slot]}）。"
    )

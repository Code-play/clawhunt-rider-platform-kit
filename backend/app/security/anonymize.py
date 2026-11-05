"""脱敏（PII 识别 / 掩码 / 合成样本 / 召回跑分）。

设计目标（与验收点 6、9 对应）：
- 手机号、身份证号召回 100%；姓名、地址召回 >= 95%；
- 误报率在合成负样本上足够低；
- 同一个 mask 函数既用于「列表掩码」也用于「送模型前脱敏」，
  送模型的占位符形如 〔phone_1〕〔name_1〕〔id_1〕〔addr_1〕。

全部规则是确定性的（不依赖网络/模型），合成样本由固定随机种子生成。
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

PiiType = Literal["phone", "id_card", "name", "address"]
PLACEHOLDER_TAG = {"phone": "phone", "id_card": "id", "name": "name", "address": "addr"}

# ---------------------------------------------------------------------------
# 基础词典（合成数据用，不含真实个人信息）
# ---------------------------------------------------------------------------
SURNAMES = (
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾萧田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
)
COMPOUND_SURNAMES = ("欧阳", "司马", "上官", "诸葛", "东方", "尉迟", "皇甫", "南宫", "慕容")
GIVEN_CHARS = (
    "伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛明超霞平刚桂华建国志辉鹏飞龙文武斌亮成波宇浩轩然欣怡佳琪婷雪梅兰竹"
)

PROVINCES = ("浙江省", "江苏省", "广东省", "山东省", "河南省", "四川省", "湖北省", "福建省", "安徽省", "江西省")
CITIES = ("杭州市", "南京市", "广州市", "济南市", "郑州市", "成都市", "武汉市", "福州市", "合肥市", "南昌市")
DISTRICTS = ("西湖区", "余杭区", "玄武区", "天河区", "历下区", "金水区", "武侯区", "洪山区", "鼓楼区", "青山湖区")
ROADS = ("文三路", "文一西路", "中山东路", "体育西路", "经十路", "花园路", "人民南路", "珞喻路", "五四路", "北京东路")
RESIDENCES = ("阳光花园", "翠苑小区", "金地公寓", "未来社区", "幸福里", "春江花月", "绿城桂花园")

# 常见非姓名词汇（避免把「安全帽」「白天班」识别成人名）
NAME_STOPWORDS = {
    "安全", "安全帽", "白天", "白天班", "高兴", "何时", "周末", "周围", "周边", "马上", "黄金",
    "金额", "安全帽", "安全员", "安装", "安排", "包含", "方便", "方法", "方向", "房间", "费用",
    "附近", "备注", "部分", "部门", "查询", "查看", "车主", "车辆", "成本", "成为", "同意",
    "同时", "同事", "任何", "任务", "日期", "日常", "容易", "商圈", "上岗", "申请", "时间",
    "日前", "如果", "入住", "上班", "上门", "上面", "上周", "设计", "身高", "身份", "身体",
    "是否", "收到", "手机", "数量", "说明", "司机", "所有", "他人", "完成", "网站", "位置",
    "姓名", "现金", "项目", "消息", "小时", "小区", "小时工", "需要", "许多", "学习", "要求",
    "一般", "一次", "已经", "应聘", "用户", "优势", "由于", "员工", "责任", "招聘", "正常",
    "证明", "直接", "之前", "之后", "职业", "只要", "地址", "登记", "电瓶车", "订单", "编号",
}

ADDRESS_MARKERS_ADMIN = ("省", "市", "区", "县", "镇", "村")
ADDRESS_MARKERS_STREET = ("路", "街", "巷", "弄", "道", "大道")
ADDRESS_MARKERS_DETAIL = ("号", "栋", "单元", "室", "楼", "层")
ADDRESS_MARKERS_AREA = ("小区", "大厦", "公寓", "广场", "花园", "社区", "里")
ADDRESS_PREFIXES = (
    "我现住在", "我住在", "现在我住", "现居住于", "居住于", "住在", "现住", "家住", "家在",
    "地址是", "地址为", "地址", "现地址", "位置在", "地点在", "工作在", "住在：", "地址：",
    "地址:",
)
ADDRESS_SUFFIXES = ("附近", "这边", "那边", "附近工作", "这一带", "周边", "附近找活")

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CARD_RE = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")
RUN_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]+")

NAME_CORE = rf"(?:{'|'.join(COMPOUND_SURNAMES)}|[{SURNAMES}])[\u4e00-\u9fa5]{{1,2}}"
NAME_CONTEXT_RE = re.compile(
    rf"(?:我叫作|我叫|名字叫|名字是|姓名是|姓名[：:]?\s*|联系人[：:]?\s*|求职者[：:]?\s*|我是|本人)"
    rf"\s*({NAME_CORE})"
)
NAME_STANDALONE_RE = re.compile(rf"(?<![\u4e00-\u9fa5])({NAME_CORE})(?![\u4e00-\u9fa5])")


@dataclass(frozen=True)
class PIIMatch:
    type: PiiType
    start: int
    end: int
    value: str


@dataclass
class MaskResult:
    text: str
    matches: list[PIIMatch] = field(default_factory=list)
    placeholders: dict[str, str] = field(default_factory=dict)  # 占位符 -> 原文

    def placeholder_for(self, value: str) -> str | None:
        for placeholder, raw in self.placeholders.items():
            if raw == value:
                return placeholder
        return None


# ---------------------------------------------------------------------------
# 身份证校验位
# ---------------------------------------------------------------------------
_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = "10X98765432"


def is_valid_id_card(value: str) -> bool:
    if len(value) != 18:
        return False
    body = value[:17]
    if not body.isdigit():
        return False
    total = sum(int(digit) * weight for digit, weight in zip(body, _ID_WEIGHTS))
    return _ID_CHECK[total % 11] == value[17].upper()


# ---------------------------------------------------------------------------
# 识别
# ---------------------------------------------------------------------------
def _find_phones(text: str) -> list[PIIMatch]:
    return [PIIMatch("phone", m.start(), m.end(), m.group(0)) for m in PHONE_RE.finditer(text)]


def _find_id_cards(text: str) -> list[PIIMatch]:
    matches: list[PIIMatch] = []
    for m in ID_CARD_RE.finditer(text):
        if is_valid_id_card(m.group(1)):
            matches.append(PIIMatch("id_card", m.start(), m.end(), m.group(1)))
    return matches


def _find_names(text: str, occupied: list[tuple[int, int]]) -> list[PIIMatch]:
    matches: list[PIIMatch] = []
    for m in NAME_CONTEXT_RE.finditer(text):
        value = m.group(1)
        if value in NAME_STOPWORDS or _overlaps(m.start(1), m.end(1), occupied):
            continue
        matches.append(PIIMatch("name", m.start(1), m.end(1), value))
    for m in NAME_STANDALONE_RE.finditer(text):
        value = m.group(1)
        if len(value) < 3 or value in NAME_STOPWORDS:
            continue
        if _overlaps(m.start(1), m.end(1), occupied):
            continue
        if any(other.value == value for other in matches):
            continue
        matches.append(PIIMatch("name", m.start(1), m.end(1), value))
    return matches


def _overlaps(start: int, end: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(start < other_end and end > other_start for other_start, other_end in spans)


def _trim_address(run: str) -> str:
    value = run
    changed = True
    while changed:
        changed = False
        for prefix in sorted(ADDRESS_PREFIXES, key=len, reverse=True):
            if value.startswith(prefix):
                value = value[len(prefix) :]
                changed = True
    for suffix in sorted(ADDRESS_SUFFIXES, key=len, reverse=True):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value


def _looks_like_address(value: str) -> bool:
    if len(value) < 6:
        return False
    admin = sum(1 for marker in ADDRESS_MARKERS_ADMIN if marker in value)
    street = sum(1 for marker in ADDRESS_MARKERS_STREET if marker in value)
    detail = sum(1 for marker in ADDRESS_MARKERS_DETAIL if marker in value)
    area = sum(1 for marker in ADDRESS_MARKERS_AREA if marker in value)
    return (admin >= 1 and (street >= 1 or detail >= 1 or area >= 1)) or (street >= 1 and detail >= 1)


def _find_addresses(text: str, occupied: list[tuple[int, int]]) -> list[PIIMatch]:
    matches: list[PIIMatch] = []
    for run in RUN_RE.finditer(text):
        raw = run.group(0)
        candidate = _trim_address(raw)
        if not _looks_like_address(candidate):
            continue
        offset = run.start() + (len(raw) - len(candidate))
        start, end = offset, offset + len(candidate)
        if _overlaps(start, end, occupied):
            continue
        matches.append(PIIMatch("address", start, end, candidate))
    return matches


def find_pii(text: str) -> list[PIIMatch]:
    """按固定优先级识别 PII，返回不重叠的命中区间。"""
    matches = _find_phones(text)
    matches.extend(_find_id_cards(text))
    matches.sort(key=lambda item: (item.start, item.end))

    occupied = [(item.start, item.end) for item in matches]
    for match in _find_names(text, occupied):
        matches.append(match)
    occupied = [(item.start, item.end) for item in matches]
    for match in _find_addresses(text, occupied):
        matches.append(match)

    matches.sort(key=lambda item: item.start)
    # 去重叠（保持先入为主：手机号/身份证优先）
    result: list[PIIMatch] = []
    last_end = -1
    for match in matches:
        if match.start < last_end:
            continue
        result.append(match)
        last_end = match.end
    return result


def mask_text(text: str) -> MaskResult:
    """把文本中的 PII 替换成 〔phone_1〕 这类占位符（送模型前必须调用）。"""
    matches = find_pii(text)
    counters: dict[str, int] = {}
    pieces: list[str] = []
    cursor = 0
    placeholders: dict[str, str] = {}
    for match in matches:
        tag = PLACEHOLDER_TAG[match.type]
        counters[tag] = counters.get(tag, 0) + 1
        placeholder = f"〔{tag}_{counters[tag]}〕"
        placeholders[placeholder] = match.value
        pieces.append(text[cursor : match.start])
        pieces.append(placeholder)
        cursor = match.end
    pieces.append(text[cursor:])
    return MaskResult(text="".join(pieces), matches=matches, placeholders=placeholders)


def mask_for_display(text: str) -> str:
    return mask_text(text).text


# ---------------------------------------------------------------------------
# 合成样本（确定性；用于召回跑分与种子数据）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SyntheticSample:
    text: str
    expected: tuple[tuple[str, str], ...]  # (pii_type, value)

    def as_dict(self) -> dict[str, object]:
        return {"text": self.text, "expected": [{"type": t, "value": v} for t, v in self.expected]}


def make_phone(rng: random.Random) -> str:
    prefixes = ("138", "139", "137", "136", "135", "150", "151", "152", "157", "158", "159", "182", "183", "187", "188", "189", "133", "177")
    return rng.choice(prefixes) + "".join(str(rng.randint(0, 9)) for _ in range(8))


def make_id_card(rng: random.Random) -> str:
    area_codes = ("110105", "310104", "330106", "440106", "320102", "370102", "410105", "510107")
    birth = f"{rng.randint(1970, 2004)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    prefix = rng.choice(area_codes) + birth + "".join(str(rng.randint(0, 9)) for _ in range(3))
    total = sum(int(digit) * weight for digit, weight in zip(prefix, _ID_WEIGHTS))
    return prefix + _ID_CHECK[total % 11]


def make_name(rng: random.Random) -> str:
    surname = rng.choice(COMPOUND_SURNAMES) if rng.random() < 0.06 else rng.choice(SURNAMES)
    given_len = 2
    return surname + "".join(rng.choice(GIVEN_CHARS) for _ in range(given_len))


def make_address(rng: random.Random) -> str:
    return (
        rng.choice(PROVINCES)
        + rng.choice(CITIES)
        + rng.choice(DISTRICTS)
        + rng.choice(ROADS)
        + str(rng.randint(1, 300))
        + "号"
        + (rng.choice(RESIDENCES) + str(rng.randint(1, 30)) + "栋" + str(rng.randint(101, 2500)) + "室" if rng.random() < 0.3 else "")
    )


def generate_samples(count: int = 200, seed: int = 20261105) -> list[SyntheticSample]:
    rng = random.Random(seed)
    samples: list[SyntheticSample] = []
    templates = (
        "你好，我叫{name}，手机号{phone}，{address}，想应聘全职骑手。",
        "姓名：{name}，联系电话：{phone}，身份证号{id_card}，现住{address}。",
        "我是{name}，{phone}，想在{address}附近找兼职，有电动车。",
        "求职者 {name}，手机 {phone}，地址 {address}，最快下周一可以到岗。",
        "姓名{name} 电话{phone} 身份证{id_card} 住址{address} 学历高中",
        "我叫{name}，身份证{id_card}，电话{phone}，目前住在{address}。",
        "联系人：{name}，{phone}，{address}，健康证正在办理。",
        "我是{name}，手机{phone}，家住{address}，周末可面试。",
        "我叫{name}，{phone}，身份证{id_card}，住在{address}。",
        "姓名：{name}，电话：{phone}，{address}，希望做夜班。",
    )
    for index in range(count):
        template = templates[index % len(templates)]
        name = make_name(rng)
        phone = make_phone(rng)
        id_card = make_id_card(rng)
        address = make_address(rng)
        text = template.format(name=name, phone=phone, id_card=id_card, address=address)
        expected: list[tuple[str, str]] = [("name", name), ("phone", phone)]
        if "{id_card}" in template:
            expected.append(("id_card", id_card))
        if "{address}" in template:
            expected.append(("address", address))
        samples.append(SyntheticSample(text=text, expected=tuple(expected)))
    return samples


NEGATIVE_TEMPLATES = (
    "订单编号 {digits} 已提交，请等待系统审核。",
    "安全帽已发放，白天班次 9 点开始，请提前 10 分钟到站。",
    "招聘骑手 {num} 名，工作地点在站点，月薪 {salary} 元。",
    "月薪 {salary} 元，每月 15 号结算，绩效另计。",
    "系统提示：您有 {num} 条消息未读，请及时处理。",
    "本单配送距离 {digits} 米，预计 {num} 分钟送达。",
    "社保缴纳基数按当地政策执行，具体以社保局公告为准。",
    "今天单量 {num} 单，超时 {num} 单，合格率 98%。",
    "电动车电量剩余 80%，请及时充电，注意行车安全。",
    "面试时间为周一下午两点，地点在站点二楼会议室。",
    "健康证办理流程：体检、领证、上传，约需 {num} 个工作日。",
    "薪资结构为基础单价加补贴，恶劣天气另计。",
    "政策更新版本 v1.2，自 2026 年 1 月 1 日起执行。",
    "请携带身份证原件到站点办理入职手续。",
)


def generate_negatives(count: int = 200, seed: int = 20261105) -> list[str]:
    rng = random.Random(seed + 1)
    negatives: list[str] = []
    for index in range(count):
        template = NEGATIVE_TEMPLATES[index % len(NEGATIVE_TEMPLATES)]
        negatives.append(
            template.format(
                digits="".join(str(rng.randint(0, 9)) for _ in range(18)),
                num=rng.randint(2, 500),
                salary=rng.choice((6000, 7000, 8000, 9000, 12000)),
            )
        )
    return negatives


# ---------------------------------------------------------------------------
# 跑分
# ---------------------------------------------------------------------------
def _covered(expected: str, detected: list[PIIMatch], pii_type: str) -> bool:
    for match in detected:
        if match.type != pii_type:
            continue
        if expected in match.value or match.value in expected:
            return True
    return False


def evaluate(samples: list[SyntheticSample] | None = None, negatives: list[str] | None = None) -> dict[str, object]:
    """返回脱敏召回/误报指标（JSON 可序列化）。"""
    samples = samples or generate_samples()
    negatives = negatives or generate_negatives()
    per_type: dict[str, dict[str, int | float]] = {}
    failures: list[dict[str, object]] = []

    for pii_type in ("phone", "id_card", "name", "address"):
        relevant = 0
        hit = 0
        for sample in samples:
            expected_values = [value for pii, value in sample.expected if pii == pii_type]
            if not expected_values:
                continue
            relevant += 1
            detected = find_pii(sample.text)
            if all(_covered(value, detected, pii_type) for value in expected_values):
                hit += 1
            elif len(failures) < 10:
                failures.append({"text": sample.text, "missing_type": pii_type, "expected": expected_values})
        per_type[pii_type] = {
            "samples": relevant,
            "hit": hit,
            "recall": round(hit / relevant, 4) if relevant else 1.0,
        }

    false_positive_samples = 0
    false_positive_hits: list[dict[str, object]] = []
    for text in negatives:
        detected = find_pii(text)
        if detected:
            false_positive_samples += 1
            if len(false_positive_hits) < 10:
                false_positive_hits.append(
                    {"text": text, "detected": [{"type": m.type, "value": m.value} for m in detected]}
                )

    result = {
        "samples": len(samples),
        "negatives": len(negatives),
        "recall": {pii_type: stats["recall"] for pii_type, stats in per_type.items()},
        "per_type": per_type,
        "false_positive_samples": false_positive_samples,
        "false_positive_rate": round(false_positive_samples / len(negatives), 4) if negatives else 0.0,
        "failures": failures,
        "false_positive_examples": false_positive_hits,
        "sample_fingerprint": hashlib.sha256(
            json.dumps([s.as_dict() for s in samples[:5]], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
    }
    return result


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))

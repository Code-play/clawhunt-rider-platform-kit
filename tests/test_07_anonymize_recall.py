"""验收点 6：脱敏库召回（手机号/身份证 100%，姓名/地址 >=95%，并输出误报率）。

纯单元测试：不依赖数据库，合成样本由固定随机种子确定性生成。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.security import anonymize


@pytest.fixture(scope="module")
def metrics() -> dict:
    return anonymize.evaluate()


def test_anonymize_sample_size_is_at_least_200(metrics):
    assert metrics["samples"] >= 200
    assert metrics["negatives"] >= 200


def test_phone_and_id_card_recall_is_100_percent(metrics):
    assert metrics["recall"]["phone"] == 1.0
    assert metrics["recall"]["id_card"] == 1.0
    assert metrics["per_type"]["id_card"]["samples"] > 0


def test_name_and_address_recall_at_least_95_percent(metrics):
    assert metrics["recall"]["name"] >= 0.95
    assert metrics["recall"]["address"] >= 0.95


def test_false_positive_rate_is_reported_and_low(metrics):
    assert "false_positive_rate" in metrics
    assert metrics["false_positive_rate"] <= 0.01


def test_mask_text_replaces_pii_with_placeholders_and_keeps_no_raw_value():
    sample = anonymize.generate_samples(1, seed=7)[0]
    masked = anonymize.mask_text(sample.text)
    raw_values = [value for _, value in sample.expected]
    for value in raw_values:
        assert value not in masked.text, f"原文泄漏: {value}"
    assert "〔phone_1〕" in masked.text
    assert "〔name_1〕" in masked.text
    for placeholder, raw in masked.placeholders.items():
        assert placeholder.startswith("〔")
        assert raw in raw_values


def test_mask_text_marks_every_detected_span():
    valid_id = anonymize.make_id_card(__import__("random").Random(11))
    text = f"我叫王小明，手机号13800138000，身份证{valid_id}"
    masked = anonymize.mask_text(text)
    assert "13800138000" not in masked.text
    assert valid_id not in masked.text
    types = {match.type for match in masked.matches}
    assert {"phone", "name", "id_card"} <= types


def test_detector_ignores_non_pii_operational_text():
    negative = "订单编号 2023110512345678 已提交，安全帽已发放，白天班次 9 点开始。"
    assert anonymize.find_pii(negative) == []


def test_id_card_checksum_is_validated():
    assert anonymize.is_valid_id_card(anonymize.make_id_card(__import__("random").Random(5)))
    assert not anonymize.is_valid_id_card("110105199001011234")

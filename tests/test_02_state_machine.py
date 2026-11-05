"""验收点 1：候选人状态机 —— 全 8x8 状态对数据驱动矩阵。"""

from __future__ import annotations

import itertools

import pytest

from app.services.candidates import ALLOWED_TRANSITIONS, CANDIDATE_STATUSES
from conftest import API, create_candidate, unique_phone

ALL_PAIRS = list(itertools.product(CANDIDATE_STATUSES, repeat=2))

# 人工审阅过的合法流转蓝图（与实现解耦，防止实现任意放宽）
EXPECTED_ALLOWED_PAIRS = {
    ("new", "collecting"),
    ("collecting", "complete"),
    ("collecting", "rejected"),
    ("collecting", "handoff"),
    ("complete", "booked"),
    ("complete", "rejected"),
    ("complete", "handoff"),
    ("booked", "interviewed"),
    ("booked", "rejected"),
    ("booked", "complete"),
    ("booked", "handoff"),
    ("interviewed", "hired"),
    ("interviewed", "rejected"),
    ("interviewed", "handoff"),
    ("hired", "handoff"),
}


async def test_state_machine_covers_all_64_state_pairs(client, admin, app):
    """遍历全部 8x8 状态对：合法流转通过、非法流转 409 且不改库。"""
    assert len(ALL_PAIRS) == 64
    allowed_pairs = {
        (source, target)
        for source in CANDIDATE_STATUSES
        for target in ALLOWED_TRANSITIONS[source]
    }
    assert allowed_pairs == EXPECTED_ALLOWED_PAIRS

    failures: list[str] = []
    for index, (source, target) in enumerate(ALL_PAIRS):
        candidate = await create_candidate(
            client, admin, name="王小明", phone=unique_phone(1000 + index)
        )
        await app.state.db.execute(
            "UPDATE candidates SET status = $2 WHERE id = $1", candidate["id"], source
        )
        response = await client.post(
            f"{API}/candidates/{candidate['id']}/status",
            json={"status": target},
            headers=admin,
        )
        allowed = (source, target) in EXPECTED_ALLOWED_PAIRS
        if allowed:
            if response.status_code != 200 or response.json()["status"] != target:
                failures.append(f"{source}->{target}: 应通过，实际 {response.status_code} {response.text}")
        else:
            body = response.json()
            if response.status_code != 409 or body.get("code") != "invalid_transition":
                failures.append(f"{source}->{target}: 应 409 invalid_transition，实际 {response.status_code} {body}")
            current = await app.state.db.fetchval(
                "SELECT status FROM candidates WHERE id = $1", candidate["id"]
            )
            if current != source:
                failures.append(f"{source}->{target}: 非法流转却改了库 -> {current}")
    assert not failures, "状态机矩阵不通过:\n" + "\n".join(failures)


async def test_terminal_statuses_reject_every_transition(client, admin, app):
    for index, source in enumerate(("hired", "handoff", "rejected")):
        candidate = await create_candidate(client, admin, phone=unique_phone(2000 + index))
        await app.state.db.execute(
            "UPDATE candidates SET status = $2 WHERE id = $1", candidate["id"], source
        )
        if source == "hired":
            allowed_targets = {"handoff"}
        else:
            allowed_targets = set()
        for target in CANDIDATE_STATUSES:
            response = await client.post(
                f"{API}/candidates/{candidate['id']}/status",
                json={"status": target},
                headers=admin,
            )
            if target in allowed_targets:
                assert response.status_code == 200, response.text
                continue
            assert response.status_code == 409, (source, target, response.text)
            assert response.json()["code"] == "invalid_transition"


async def test_status_transition_writes_audit_and_events(client, admin, app):
    candidate = await create_candidate(client, admin, phone=unique_phone(3000))
    for target in ("collecting", "complete", "booked"):
        response = await client.post(
            f"{API}/candidates/{candidate['id']}/status",
            json={"status": target},
            headers=admin,
        )
        assert response.status_code == 200, response.text
    actions = [
        row["action"]
        for row in await app.state.db.fetch("SELECT action FROM audit_log ORDER BY id")
    ]
    assert actions.count("candidate.status.update") == 3
    event_types = {
        row["event_type"]
        for row in await app.state.db.fetch("SELECT event_type FROM outbox_events")
    }
    assert {"candidate.created", "candidate.completed", "candidate.updated"} <= event_types


async def test_unknown_status_is_rejected(client, admin):
    candidate = await create_candidate(client, admin, phone=unique_phone(4000))
    response = await client.post(
        f"{API}/candidates/{candidate['id']}/status",
        json={"status": "flying"},
        headers=admin,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_status"

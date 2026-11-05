"""种子数据（全部合成）：员工、站点、政策文档、合成线索、脱敏样本。

- `seed_reference(...)`: 员工/站点/政策（测试每个用例前都会调用）；
- `seed_demo_data(...)`: 追加 50 条合成线索与 220 条脱敏样本（docker 一键启动时用）。
"""

from __future__ import annotations

import json
from typing import Any

from app.security import anonymize
from app.security.tokens import hash_password, make_salt
from app.security.vault import Vault
from app.services import policies

SEED_EMPLOYEES = (
    ("admin", "admin123", "admin", "*", ()),
    ("A1024", "123456", "admin", "*", ()),
    ("sh_manager", "sh123456", "city_manager", "上海", ()),
    ("bj_manager", "bj123456", "city_manager", "北京", ()),
    ("sh_viewer", "view123456", "viewer", "上海", ()),
    ("sh_ops", "ops123456", "station_operator", "上海", ("徐汇站", "浦东站")),
)

SEED_STATIONS = (
    {
        "name": "徐汇站",
        "city": "上海",
        "area": "徐汇区",
        "lat": 31.188,
        "lng": 121.436,
        "open_quota": 10,
        "address": "徐汇区漕溪北路 88 号",
        "distance_km": 1.2,
        "manager_virtual_no": "4000001001",
        "manager_display_no": "400-000-1001",
        "slot_capacity": 100,
    },
    {
        "name": "浦东站",
        "city": "上海",
        "area": "浦东新区",
        "lat": 31.230,
        "lng": 121.544,
        "open_quota": 10,
        "address": "浦东新区张江路 66 号",
        "distance_km": 2.4,
        "manager_virtual_no": "4000001002",
        "manager_display_no": "400-000-1002",
        "slot_capacity": 100,
    },
    {
        "name": "朝阳站",
        "city": "北京",
        "area": "朝阳区",
        "lat": 39.921,
        "lng": 116.443,
        "open_quota": 10,
        "address": "朝阳区朝阳路 100 号",
        "distance_km": 3.1,
        "manager_virtual_no": "4000001003",
        "manager_display_no": "400-000-1003",
        "slot_capacity": 100,
    },
)

SEED_POLICY_DOCS = (
    (
        "骑手招募政策手册",
        "v1.2",
        "年龄与身份要求",
        "年龄要求：年满18周岁、不超过60周岁；须持有效身份证件；未满18周岁不得录用为骑手。",
        "2026-01-01",
        "以上为政策摘要，具体以站点公示与合作协议为准。",
    ),
    (
        "骑手招募政策手册",
        "v1.2",
        "健康证要求",
        "健康证要求：全职骑手须在入职前取得健康证，办理流程为体检、领证、上传系统，约需3个工作日；正在办理者可先登记。",
        "2026-01-01",
        "以上为政策摘要，具体以站点公示与合作协议为准。",
    ),
    (
        "薪酬与结算办法",
        "v2.0",
        "薪资结构",
        "薪资结构：基础单价加补贴；结算规则：全职骑手每月15号结算，兼职骑手按周结算，恶劣天气补贴另计。",
        "2026-05-01",
        "以上为规则摘要，最终以站点《报酬结算确认单》为准。",
    ),
    (
        "电动车与装备规范",
        "v1.4",
        "车辆要求",
        "车辆要求：骑手可自备电动车，也可使用站点共享车辆；自备车辆须符合当地上牌与安全标准。",
        "2026-03-01",
        "以上为摘要，具体以当地交管规定为准。",
    ),
    (
        "站点分配与住宿政策",
        "v1.0",
        "站点分配规则",
        "站点分配规则：按居住区域就近分配，站点名额已满时由系统轮询至相邻站点。",
        "2026-02-01",
        "以上为摘要，具体以站点通知为准。",
    ),
    (
        "个人信息保护与保留期政策",
        "v1.1",
        "保留期与删除",
        "隐私政策规定：我们仅收集招聘匹配所必需的信息，姓名与手机号以令牌化方式存储；保留期：未录用候选人信息保留90天；对话原文保留30天；未成年人信息24小时内删除。",
        "2026-09-01",
        "以上为摘要，完整条款以《个人信息收集告知书》为准。",
    ),
    (
        "骑手合作保障与商业保险说明",
        "v2026.3",
        "保险保障",
        "保险保障：平台为完成实名认证且当日接单的骑手投保当日意外险，含意外身故/伤残与意外医疗；接单当日生效、次日零时失效，无需骑手付费。",
        "2026-03-01",
        "以上为政策摘要，具体保障范围与理赔流程以承保保险公司条款为准。",
    ),
    (
        "骑手到站与入职流程说明",
        "v2026.1",
        "到站与入职流程",
        "到站与入职流程：携带本人身份证、健康证（食品配送岗位）与可正常使用的智能手机；签到、资料核验、安全培训约40分钟、装备领取、跟车试跑。",
        "2026-02-01",
        "不同站点流程略有差异，请以预约成功后站长电话通知为准。",
    ),
)

_SEED_STATUS_PLAN = (
    ("new", 20),
    ("collecting", 10),
    ("complete", 8),
    ("booked", 4),
    ("interviewed", 3),
    ("hired", 2),
    ("rejected", 2),
    ("handoff", 1),
)


async def seed_reference(db: Any, vault: Vault, settings: Any, clock: Any) -> None:
    """幂等：仅当对应表为空时写入。测试与 docker 启动共用。"""
    station_count = await db.fetchval("SELECT count(*) FROM stations")
    if station_count == 0:
        async with db.transaction() as conn:
            for station in SEED_STATIONS:
                await conn.execute(
                    """
                    INSERT INTO stations
                        (name, city, area, lat, lng, open_quota, address, distance_km,
                         manager_virtual_no, manager_display_no, slot_capacity)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    station["name"],
                    station["city"],
                    station["area"],
                    station["lat"],
                    station["lng"],
                    station["open_quota"],
                    station["address"],
                    station["distance_km"],
                    station["manager_virtual_no"],
                    station["manager_display_no"],
                    station["slot_capacity"],
                )
    # 旧库回填：新增展示字段（幂等）
    for station in SEED_STATIONS:
        await db.execute(
            """
            UPDATE stations
            SET address = coalesce(address, $2),
                distance_km = CASE WHEN distance_km = 0 THEN $3 ELSE distance_km END,
                manager_virtual_no = coalesce(manager_virtual_no, $4),
                manager_display_no = coalesce(manager_display_no, $5),
                slot_capacity = CASE WHEN slot_capacity < 10 THEN $6 ELSE slot_capacity END
            WHERE name = $1
            """,
            station["name"],
            station["address"],
            station["distance_km"],
            station["manager_virtual_no"],
            station["manager_display_no"],
            station["slot_capacity"],
        )
    employee_count = await db.fetchval("SELECT count(*) FROM employees")
    if employee_count == 0:
        station_rows = await db.fetch("SELECT name, id FROM stations")
        station_ids = {row["name"]: row["id"] for row in station_rows}
        async with db.transaction() as conn:
            for username, password, role, city, station_names in SEED_EMPLOYEES:
                salt = make_salt()
                await conn.execute(
                    """
                    INSERT INTO employees (username, password_hash, salt, display_name, role, city, station_ids)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::uuid[])
                    ON CONFLICT (username) DO NOTHING
                    """,
                    username,
                    hash_password(password, salt),
                    salt,
                    "张敏" if username == "A1024" else username,
                    role,
                    city,
                    [station_ids[name] for name in station_names if name in station_ids],
                )
    # 演示工号 A1024（前端预填账号）在旧库里也要补上
    salt = make_salt()
    await db.execute(
        """
        INSERT INTO employees (username, password_hash, salt, display_name, role, city, station_ids)
        VALUES ('A1024', $1, $2, '张敏', 'admin', '*', '{}'::uuid[])
        ON CONFLICT (username) DO NOTHING
        """,
        hash_password("123456", salt),
        salt,
    )
    policy_count = await db.fetchval("SELECT count(*) FROM policy_docs")
    if policy_count == 0:
        async with db.transaction() as conn:
            for doc_name, version, section, chunk, effective_date, disclaimer in SEED_POLICY_DOCS:
                await policies.upsert_policy_doc(
                    conn,
                    doc_name=doc_name,
                    doc_version=version,
                    section=section,
                    chunk=chunk,
                    effective_date=effective_date,
                    disclaimer=disclaimer,
                )
    else:
        # 旧库回填新政策文档（幂等 upsert）
        async with db.transaction() as conn:
            for doc_name, version, section, chunk, effective_date, disclaimer in SEED_POLICY_DOCS:
                await policies.upsert_policy_doc(
                    conn,
                    doc_name=doc_name,
                    doc_version=version,
                    section=section,
                    chunk=chunk,
                    effective_date=effective_date,
                    disclaimer=disclaimer,
                )


async def seed_demo_data(db: Any, vault: Vault, settings: Any, clock: Any) -> None:
    """演示/一键启动用：50 条合成线索 + 220 条脱敏样本（幂等）。"""
    candidate_count = await db.fetchval("SELECT count(*) FROM candidates")
    if candidate_count == 0:
        rng_samples = anonymize.generate_samples(80, seed=20261106)
        stations = await db.fetch("SELECT id, city FROM stations ORDER BY name")
        async with db.transaction() as conn:
            sample_index = 0
            for status, amount in _SEED_STATUS_PLAN:
                for _ in range(amount):
                    sample = rng_samples[sample_index % len(rng_samples)]
                    sample_index += 1
                    name = next(value for pii, value in sample.expected if pii == "name")
                    phone = next(value for pii, value in sample.expected if pii == "phone")
                    station = stations[sample_index % len(stations)] if stations else None
                    name_token = await vault.tokenize(conn, "name", name)
                    phone_token = await vault.tokenize(conn, "phone", phone)
                    await conn.execute(
                        """
                        INSERT INTO candidates
                            (name_token, phone_token, birth_ym, area_text, job_type, has_ebike, start_text,
                             health_cert, source_channel, station_id, city, status, profile_complete,
                             consent_version, consent_at, retention_until, created_at, updated_at)
                        VALUES ($1,$2,NULL,$3,'fulltime',$4,'下周','unknown','import',$5,$6,$7,$8,'v1',now(),
                                now() + interval '90 days', now(), now())
                        """,
                        name_token,
                        phone_token,
                        "杭州西湖区",
                        sample_index % 2 == 0,
                        station["id"] if station else None,
                        station["city"] if station else "上海",
                        status,
                        status in ("complete", "booked", "interviewed", "hired", "handoff"),
                    )
    sample_count = await db.fetchval("SELECT count(*) FROM synthetic_samples")
    if sample_count == 0:
        samples = anonymize.generate_samples(220, seed=20261105)
        async with db.transaction() as conn:
            for sample in samples:
                await conn.execute(
                    "INSERT INTO synthetic_samples (raw_text, expected) VALUES ($1, $2::jsonb)",
                    sample.text,
                    json.dumps(
                        [{"type": pii, "value": value} for pii, value in sample.expected],
                        ensure_ascii=False,
                    ),
                )


async def seed_if_empty(db: Any, vault: Vault, settings: Any, clock: Any) -> None:
    await seed_reference(db, vault, settings, clock)
    await seed_demo_data(db, vault, settings, clock)

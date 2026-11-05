# Rider Recruitment Agent Platform — Runnable Skeleton (Contract v1)

A **runnable, one-command skeleton** for the "AI-assisted rider recruitment information platform" project.
It implements the shared **Contract v1** (the interface contract common to all 5 tasks of the client's project split),
plus a vertical slice for every acceptance point that is normally the riskiest to demonstrate.

> 本仓库是给投标与交付用的**可运行骨架**：`docker compose up` 一条命令起全栈（API + PostgreSQL 16/pgvector + Valkey + 两个前端），
> 每个关键验收点都有可复跑的自动化断言，不依赖任何真实密钥或外部大模型（默认 `LLM_MODE=mock`，确定性输出）。

- 后端：Python 3.12 + FastAPI，`/api/v1` 前缀、统一错误体 `{code, message}`、自动 OpenAPI 文档
- 数据：PostgreSQL 16（pgvector 向量列）+ Valkey 8（缓存/幂等）
- 前端：React 18 + Vite 6（H5 求职者端）、React 18 + Ant Design 5（招聘工作台/驾驶舱）
- 许可：依赖全部为 MIT / Apache-2.0 / BSD / PostgreSQL，无 GPL/AGPL（有测试断言）

---

## 1. Quick start（一条命令）

```bash
docker compose up -d --build
```

起好后：

| 入口 | 地址 | 说明 |
| --- | --- | --- |
| H5 求职者端 | http://127.0.0.1:8081/h5/ | 渠道进线 → 告知同意 → 7 项对话 → 政策问答 → 站点推荐 → 预约 → 结果页 → 个人信息自助 |
| 招聘工作台 / 驾驶舱 | http://127.0.0.1:8081/admin/ | 登录 `A1024 / 123456`（种子数据）；候选人列表默认掩码、解盲需理由并写审计 |
| API | http://127.0.0.1:8000/api/v1 | 契约 v1 端点 |
| API 文档（OpenAPI） | http://127.0.0.1:8000/api/v1/docs | 自动生成，可直接 Try it out |
| 健康检查 | http://127.0.0.1:8000/api/v1/health | 真实探测 db 与 cache |

前端经 nginx `/proxy` 同源反代后端（无跨域），页面会显示当前数据来源（`真后端 fetch` / `内置 mock`）；
后端不可用时自动回落内置 mock，保证演示不白屏。端口可用 `.env` 的 `WEB_PORT` 覆盖（默认 8081——本机 8080 常被代理占用）。

演示账号（种子数据）：`A1024 / 123456`（admin）、`admin / admin123`、`sh_manager / sh123456`、`bj_manager / bj123456`。

只想起依赖、在本机跑测试：

```bash
docker compose up -d db cache
```

停止：`docker compose down`；连数据一起清掉：`docker compose down -v`。

---

## 2. Tests（一条命令）

```bash
# 依赖（uv 建 venv；也可用任意 Python 3.12 环境）
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r backend/requirements-dev.txt

# 起 db + cache 后跑测试（测试会自建 rider_test 库）
docker compose up -d db cache
.venv/Scripts/python.exe -m pytest tests -q
# 实测：77 passed, 0 failed（约 62s；时间相关用例用注入时钟，不等待真实时间）
```

覆盖的验收点：

| # | 验收点 | 测试 |
| --- | --- | --- |
| 1 | 候选人 12 态状态机：合法通过 / 非法拒绝，**全部状态对**数据驱动 | `tests/test_02_state_machine.py` |
| 2 | 线索导入 100 条（含重复）去重正确、分配规则生效 | `tests/test_03_lead_import.py` |
| 3 | **50 并发抢最后 5 个名额，恰好 5 成功**（库级原子扣减，不超卖） | `tests/test_04_booking_oversell.py` |
| 4 | 状态变更写 outbox + HMAC-SHA256 签名 + 重试退避 + 重复投递幂等 | `tests/test_05_webhooks.py` |
| 5 | 列表默认掩码；解盲需权限 + 理由并写只追加审计 | `tests/test_06_masking_vault.py` |
| 6 | 中文脱敏召回（手机/身份证/姓名/地址）与误报率，≥200 条合成样本 | `tests/test_07_anonymize_recall.py` |
| 7 | 对话引擎：7 槽位、口语抽取（「91 年 5 月」→ `1991-05`）、未满 18 岁 `end_minor`、主模型超时降级表单模式 | `tests/test_08_agent_dialog.py` |
| 8 | 送模型前脱敏：mock LLM 记录请求体，断言不含原文、只含 `〔phone_1〕` 类占位符 | `tests/test_09_llm_payload_masking.py` |
| 9 | 政策知识库：pgvector + 关键词混合检索，每条带出处；无命中转人工不编造 | `tests/test_10_policies.py` |
| 10 | 7 项 KPI 单点定义（SQL 视图），API 读数与视图逐项相等 | `tests/test_11_kpi.py` |
| 11 | 只追加哈希链审计：篡改任一行可定位到该行 | `tests/test_12_audit_chain.py` |
| 12 | 保留期与删除（未录用 90 天 / 对话 30 天 / 未成年 24 小时），**可注入时钟** | `tests/test_13_retention.py` |
| 13 | RBAC + 城市/站点数据域：跨域越权拒绝且不泄漏字段 | `tests/test_14_rbac.py` |
| 14 | 健康检查与 OpenAPI 可用 | `tests/test_01_health.py` |
| 15 | 依赖许可白名单（无 GPL/AGPL） | `tests/test_15_dependencies_license.py` |
| 16 | 前端契约路径兼容层（登录/同意/管理端动作/导出/撤回） | `tests/test_16_frontend_contract_compat.py` |

脱敏召回跑分（独立脚本，输出 JSON 指标）：

```bash
.venv/Scripts/python.exe backend/scripts/eval_anonymize.py
```

---

## 3. Repository layout

```
backend/                 FastAPI 服务（api / services / agent / events / security / db）
  app/db/init.sql        建表、pgvector 扩展、KPI 视图（幂等）
  app/db/seed.py         合成种子数据（员工、3 站点、政策文档、线索、脱敏样本）
  scripts/eval_anonymize.py  脱敏召回/误报跑分
web/                     npm workspace
  h5/                    求职者端（React + Vite）
  admin/                 招聘工作台 + 驾驶舱（React + AntD）
  Dockerfile, nginx.conf 构建两个前端并由 nginx 托管 + 同源反代后端
tests/                   pytest：上述验收点
docs/backend.md          端点清单、环境变量、实现说明、已知未做项
docs/web.md              前端启动、mock/真后端切换、页面与未做项
docker-compose.yml       db(pgvector) + cache(valkey) + api + web
```

---

## 4. Contract v1 (implemented subset)

- REST `/api/v1`，JSON，错误体 `{code, message}`；员工端 Bearer JWT，求职者端会话令牌
- `candidate`：`id, name_token, phone_token, birth_ym, area_text, job_type, has_ebike, start_text, experience_text, health_cert, source_channel, station_id, status, consent_version, consent_at, retention_until, created_at, updated_at`
- `station`：`id, name, lat, lng, open_quota`；`booking`：`id, candidate_id, station_id, slot_start, status`
- 事件：`candidate.created/updated/completed`、`booking.created/cancelled`、`handoff.requested`（outbox + Webhook，HMAC-SHA256）
- Agent 会话：`POST /agent/sessions`、`POST /agent/sessions/{id}/messages` → `{reply, quick_replies, progress, actions}`，
  `actions ∈ show_stations | booking_confirmed | handoff | end_minor`
- 保险箱：`POST /vault/tokenize`、`POST /vault/detokenize`（需权限 + 理由 + 审计）；掩码 `138****8000` / `王**`
- KPI：`GET /kpi/summary`（单点 SQL 视图）
- 兼容层：`/auth/login`、`/consent`、`/admin/candidates*`、`/admin/metrics`、`/admin/interviews`、`/candidates/{id}/export`、`/candidates/{id}/revoke`

完整端点表见 [`docs/backend.md`](docs/backend.md)。

---

## 5. Boundaries (honest scope)

This is a skeleton + vertical slice, not the full product. Known gaps are listed in
[`docs/backend.md`](docs/backend.md) §8 and [`docs/web.md`](docs/web.md) §6, notably:

- 不接真实短信/微信渠道；`source_channel` 只是字段
- Webhook 后台 worker 未常驻（`process_due_once` 已实现，可由 cron 触发；管理端点可手动投递）
- `LLM_MODE=openai` 只校验客户端构建，未在测试里做真网络调用（默认 mock 可零成本复跑）
- 审计链仅库内链式校验，未做外部锚定
- 前端管理端 bundle 未做路由分包；地图仅外链高德 URI
- 生产部署需替换 `.env` 里的开发默认密钥，并补网关限流/WAF

## 6. License

Code in this repository is provided for the client's evaluation and delivery.
Third-party dependencies are restricted to MIT / Apache-2.0 / BSD / PostgreSQL licenses (asserted by `tests/test_15_dependencies_license.py`).


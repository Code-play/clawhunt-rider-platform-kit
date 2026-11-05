# 后端切片说明（契约 v1）

骑手招聘 Agent 化信息收集平台的**可运行公共骨架 + 垂直切片**。技术栈：Python 3.12 + FastAPI、PostgreSQL 16（pgvector）、Valkey 8、Docker Compose。

只用合成/脱敏数据；无需真实密钥即可跑通（默认 `LLM_MODE=mock` 为确定性本地实现）。
本后端同时实现了**契约 v1 原生端点**与**前端（H5 / admin）实际调用的兼容端点**，把 `VITE_API_BASE` 指向本服务即可让两个前端走真后端、不再回落 mock。

## 1. 目录结构

```
backend/
  Dockerfile              API 镜像（python:3.12-slim）
  requirements.txt        运行依赖（版本钉住，许可 MIT/Apache-2.0/BSD）
  requirements-dev.txt    测试依赖（pytest / pytest-asyncio）
  scripts/eval_anonymize.py   脱敏召回跑分脚本（输出 JSON 指标）
  app/
    main.py               create_app()：lifespan 建池、幂等建表、种子数据
    config.py             环境变量（pydantic-settings）
    errors.py             统一错误体 {code, message}
    api/                  路由层（auth/consent/candidates/leads/stations/bookings/vault/
                          agent/policies/kpi/admin/admin-compat/health）
    models/schemas.py     请求模型（OpenAPI 自动产出）
    services/             领域服务（候选人/线索/预约/KPI/政策/保留期/审计/管理端聚合）
    events/               outbox + Webhook（HMAC 签名、指数退避、幂等）
    agent/                对话引擎、可插拔 LLM、口语槽位抽取
    security/             保险箱、掩码、脱敏、JWT/RBAC、可注入时钟
    db/init.sql           建表/扩展/触发器/KPI 视图（幂等，含旧库 ALTER 迁移）
    db/seed.py            种子数据（员工含演示工号 A1024、3 站点、8 政策文档、
                          50 线索、220 脱敏样本）
tests/                    pytest：验收点 1~14 + 前端契约兼容层，共 77 条
```

## 2. 启动

```bash
# 只用依赖（本地开发/跑测试）
docker compose up -d db cache

# 一键起全栈（api + db + cache，自动建表与种子）
docker compose up -d --build

# 健康检查
curl -s http://127.0.0.1:8000/api/v1/health
# {"status":"ok","db":"ok","cache":"ok",...}
```

OpenAPI 文档：<http://127.0.0.1:8000/api/v1/docs>（JSON：`/api/v1/openapi.json`）。

演示账号（合成）：`A1024 / 123456`（admin 前端预填）、`admin / admin123`、`sh_manager / sh123456`
（上海城市经理）、`bj_manager / bj123456`（北京）、`sh_viewer / view123456`（只读）、
`sh_ops / ops123456`（站点运营，仅徐汇/浦东）。

> 说明：Windows 上 `localhost` 可能先解析 IPv6 并等待超时（实测 21s/连接），
> 因此本仓库的本地默认地址统一写成 `127.0.0.1`。容器内仍用 compose 服务名 `db`/`cache`。

## 3. 本地测试

```bash
# 依赖（uv 建 venv，Python 3.12）
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r backend/requirements-dev.txt

# 起依赖后跑测试（测试库 rider_test 会自动 DROP/CREATE 并建好 schema）
docker compose up -d db cache
.venv/Scripts/python.exe -m pytest tests -q
# 77 passed（约 70s）
```

脱敏召回跑分：

```bash
.venv/Scripts/python.exe backend/scripts/eval_anonymize.py
# {"samples":200,"negatives":200,"recall":{"phone":1.0,"id_card":1.0,"name":1.0,"address":1.0},
#  "false_positive_rate":0.005,...}
```

## 4. 环境变量

见仓库根 `.env.example`。关键项：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://rider:rider_dev_password@127.0.0.1:55432/rider` | 容器内由 compose 覆盖为 `db:5432` |
| `CACHE_URL` | `redis://127.0.0.1:56379/0` | Valkey（Redis 协议） |
| `JWT_SECRET` | 开发默认值 | 员工端 Bearer JWT HS256 |
| `VAULT_KEY` | 开发默认值 | 保险箱密钥（确定性令牌 + Fernet 密文） |
| `WEBHOOK_SECRET` | 开发默认值 | Webhook HMAC-SHA256 签名密钥 |
| `LLM_MODE` | `mock` | `mock`=确定性本地实现；`openai`=OpenAI 兼容 `/chat/completions` |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | 空 / `gpt-4o-mini` / 空 | `openai` 模式必填 base_url |
| `LLM_TIMEOUT_SECONDS` | `5` | 超时即降级为表单式问答 |
| `AUTO_INIT` / `AUTO_SEED` | `1` | 启动时幂等建表 / 写入种子数据 |
| `CORS_ORIGINS` | `*` | 允许跨域的前端来源（逗号分隔；本地演示用 `*`，生产请收敛到 H5/admin 域名） |

生产部署必须替换三个开发默认密钥。

## 5. 端点清单（前缀 `/api/v1`）

错误体统一为 `{code, message}`；员工端点要求 `Authorization: Bearer <JWT>`。
标注「求职者自助」的端点不需要员工 JWT，候选人 id（UUID）即 capability。

### 认证 / 健康 / 告知同意

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/token` | `{username,password}` → `{access_token,...}` |
| POST | `/auth/login` | **兼容前端**：`{employee_no 或 username,password}` → `{token, user:{name,employee_no,...}}` |
| GET | `/health` | `{status, db, cache, version, llm_mode}`，真实探测 db/cache |
| POST | `/consent` | **H5**：`{consent_version, consent_at, source_channel, name?, phone?, birth_ym?, candidate_id?}` → `{candidate_id, consent_doc}`；先同意后建档 |

### 候选人

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/candidates` | 员工建档（姓名/手机号进保险箱；同手机号去重 409） |
| GET | `/candidates` | 员工列表（`status/city/station_id/limit/offset`），默认掩码 |
| GET | `/candidates/{id}` | 详情；带 JWT 走城市/站点数据域，不带 JWT 视为求职者自助 |
| PATCH | `/candidates/{id}` | 更新资料；自助模式只允许 H5 字段 |
| POST | `/candidates/{id}/status` | 状态流转；非法流转 409 `invalid_transition` |
| GET | `/candidates/{id}/export` | 信息副本（默认掩码；`include_real=true` 需员工权限并写审计） |
| POST | `/candidates/{id}/revoke` | 撤回授权并删除（级联预约/会话，归还站点名额，写审计） |

返回字段同时含 `name/phone`（掩码）与前端使用的 `name_masked/phone_masked`。

### 线索 / 站点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/leads/import` | 批量导入；按 `phone_token` 去重；`strategy=round_robin\|area\|station` |
| GET | `/stations` | **H5（免登录）**：`{stations:[{id,name,address,distance_km,open_quota,booked_count,manager_virtual_no,slots[]}]}` |
| GET | `/stations/{id}` | 单站点 + 可约时段（未来 3 天 × 09:00/13:30/16:00） |

### 预约

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/bookings` | 预约；条件 `UPDATE ... WHERE open_quota > 0` 原子扣减，满额 409 `sold_out`；返回嵌套站点 |
| GET | `/bookings` | 预约列表（匿名请求需 `candidate_id`） |
| GET | `/bookings/{id}` | 预约详情 + 站点（H5 结果页用） |
| PATCH | `/bookings/{id}` | **H5 改约**：`{slot_start}`；员工到面登记：`{status: done\|no_show}` |
| POST | `/bookings/{id}/cancel` | 取消并归还名额 |

### 保险箱

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/vault/tokenize` | `{type,value}` → `{token}`（确定性令牌，同值同 token） |
| POST | `/vault/detokenize` | 需 `vault:detokenize` + 非空 `reason`，写只追加审计 |

### Agent 会话 / 政策

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/agent/sessions` | 可带 `{candidate_id}` 绑定 H5 已建档候选人 → `{session_id, candidate_id, greeting, reply, progress, actions}` |
| POST | `/agent/sessions/{id}/messages` | `{text, client_message_id?}` → `{reply, quick_replies, progress, actions, message_id, policy_card?, source_label?, stations?}`；`client_message_id` 幂等重放返回 `replayed:true` |
| GET | `/policies/search?q=` | 向量 + 关键词混合检索，每条带文档名+版本+生效日期+免责声明；无命中 `handoff_required=true` |

`progress.fields` 为 `[{key,label,collected}]`（7 项），`done/total` 同步给出。

### 指标 / 运维 / 管理端

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/kpi/summary` | 只读 SQL 视图 `kpi_summary`（8 列覆盖 7 项指标，首响拆均值+P95） |
| GET | `/admin/metrics` | **admin**：7 KPI 卡 + 漏斗 + 渠道分布 + `kpi_metrics`（同源视图） |
| GET | `/admin/candidates` | **admin**：`q/status/source_channel/station_id/intent_level/page/page_size` → `{items,total,page,page_size}` |
| GET | `/admin/candidates/{id}` | **admin**：详情 + 资格初筛/对话摘要/转写/审计留痕/面试时段/预约 |
| PATCH | `/admin/candidates/{id}` | **admin**：`{fields, reason}`，reason 必填（≥2 字），逐字段留痕 |
| POST | `/admin/candidates/{id}/actions` | **admin**：`confirm_interview`（需 slot_start）/`handoff`/`reject`/`update_fields`，reason 必填；写「改前→改后+原因+操作人+时间」 |
| GET | `/admin/interviews?from=&to=` | **admin**：面试日程，返回 `{interviews[], items[], total}`（兼容前端两种读法） |
| GET | `/admin/stations` | **admin**：站点名额/已约/剩余/状态/可约时段 |
| PATCH | `/admin/stations/{id}` | **admin**：调整 `open_quota`（0~99）并写审计 |
| GET | `/admin/audit/detokenize` | **admin**：解盲留痕列表 |
| GET | `/admin/audit/verify` | 哈希链校验；篡改返回 `{ok:false, broken_at:<行id>}` |
| POST | `/admin/retention/run` | 执行保留期删除/原文脱敏（时间取自注入时钟） |
| GET | `/admin/outbox` | outbox 事件列表 |
| POST | `/admin/outbox/{event_id}/deliver` | 手动投递一条事件 |

## 6. 前端契约兼容层（本次联调新增）

`docs/web.md` 的 H5 / admin 两个前端按契约 v1 路径实现。为保证它们连真后端时
**不掉回 mock**，后端在不改动业务 service 的前提下补了路由别名与响应适配：

- 登录：`/auth/login` → 复用员工校验与 JWT 签发；前端读 `token`、`user.name`、`user.employee_no`。
- 告知同意：`/consent` → 先建空档（状态 collecting，姓名/手机号可后补）或更新已有档案的同意字段。
- 会话：`/agent/sessions {candidate_id}` 绑定已建档候选人；对话逐项回写档案，收齐 7 项置 complete；
  响应带 `greeting/message_id/policy_card/source_label/stations`，且 `client_message_id` 幂等。
- 站点/预约：`/stations`、`/stations/{id}` 免登录返回距离/已约/可约时段；`/bookings` 免登录可创建，
  `GET/PATCH /bookings/{id}` 支持结果页与改约。
- 自助四项：`GET /candidates/{id}`、`PATCH`、`export`、`revoke` 以候选人 UUID 为 capability，无需员工 JWT。
- 管理端：`/admin/candidates*`、`/admin/interviews`、`/admin/stations*`、`/admin/metrics`、
  `/admin/audit/detokenize` 全部走 JWT + 城市/站点数据域；动作与更正均强制 reason 并写审计留痕。

- 已启用 CORS（默认 `*`，生产收敛）：H5/admin 开发端口（4173/4174）可直连本 API。
- 管理员动作（确认面试）会真正创建 booking（占用站点名额）、更新候选人状态并写事件与审计；
拒绝/转人工会给 `retention_until` 与状态留痕，保留期规则照常生效。

## 7. 关键实现说明

- **状态机**：`backend/app/services/candidates.py::ALLOWED_TRANSITIONS` 是唯一流转定义；
  终态 `handoff` / `rejected` 拒绝一切流转，`hired` 只允许 `handoff`；员工动作里的管理端操作会按业务需要直改并留痕。
- **预约不超卖**：`UPDATE stations SET open_quota = open_quota - 1 WHERE id=$1 AND open_quota > 0 RETURNING ...`
  是库级原子扣减（行锁 + 条件更新）；另用 `uq_bookings_active_candidate` 部分唯一索引防重复预约。
- **事件**：业务写入与 `outbox_events` 同事务；`dedupe_key` 唯一约束防重复事件；
  Webhook 签名 `X-Rider-Signature: sha256=HMAC(secret, body)`，失败按 `2^n` 秒退避重试；
  `(event_id, endpoint)` 唯一约束 + 先抢占投递行实现「重复投递幂等」。
- **审计链**：`audit_log.hash = sha256(prev_hash|actor|action|resource|payload_canonical)`，
  `UPDATE/DELETE` 被触发器拒绝；`verify_chain()` 返回第一条断链行的 id。
- **脱敏**：`backend/app/security/anonymize.py` 纯规则实现；送模型前把 PII 换成
  `〔phone_1〕/〔name_1〕/〔id_1〕/〔addr_1〕`（mock LLM 会记录请求体，测试直接断言）。
- **可插拔 LLM**：`LLM_MODE=mock` 用确定性本地规则（不联网、无密钥）；`openai` 走 OpenAI 兼容接口；
  超时/网络错误降级为「表单模式」，`progress.mode="form"`。
- **保留期**：`Clock` 可注入（测试用 `FrozenClock`）。候选人以 `retention_until` 为唯一判据
  （未录用 90 天、未成年人 24 小时、已入职/已交接为 NULL 永久保留）；对话原文 30 天置空。
- **KPI 同源**：`kpi_summary` 视图单点定义，`/kpi/summary` 与 `/admin/metrics` 的 `kpi_metrics` 只做读数；
  测试断言 API 数值与视图逐项相等。

## 8. 验收点 → 测试映射

| 验收点 | 测试文件 |
| --- | --- |
| 1 状态机全状态对 | `tests/test_02_state_machine.py` |
| 2 线索导入去重/分派 | `tests/test_03_lead_import.py` |
| 3 预约不超卖（50 并发） | `tests/test_04_booking_oversell.py` |
| 4 Webhook 签名/重试/幂等 | `tests/test_05_webhooks.py` |
| 5 掩码与解盲审计 | `tests/test_06_masking_vault.py` |
| 6 脱敏召回与误报 | `tests/test_07_anonymize_recall.py` |
| 7 对话引擎 | `tests/test_08_agent_dialog.py` |
| 8 政策知识库 | `tests/test_10_policies.py` |
| 9 送模型前脱敏 | `tests/test_09_llm_payload_masking.py` |
| 10 KPI 视图一致 | `tests/test_11_kpi.py` |
| 11 哈希链审计 | `tests/test_12_audit_chain.py` |
| 12 保留期与注入时钟 | `tests/test_13_retention.py` |
| 13 RBAC 数据域 | `tests/test_14_rbac.py` |
| 14 健康检查/OpenAPI | `tests/test_01_health.py` |
| 前端契约兼容层（H5 + admin） | `tests/test_16_frontend_contract_compat.py` |
| 依赖许可白名单 | `tests/test_15_dependencies_license.py` |

## 9. 已知未做项（骨架边界）

- 未接入真实短信/微信渠道；`source_channel` 只是字段。
- Webhook 后台 worker 未常驻（`process_due_once` 已实现，可由 cron/独立进程调用）；管理端点可手动触发。
- 缓存仅用于健康检查，未做会话/热点缓存。
- LLM 的 `openai` 模式未在 CI 里做真网络调用（只校验客户端构建）；需自备 key 与 base_url。
- 审计链未做外部锚定（如每日根哈希上链/对象存储），仅库内链式校验。
- 管理端动作未做二次审批流；生产需补充网关限流与 WAF。
- 员工密码用 PBKDF2-SHA256（stdlib），未接企业 SSO。
- 站点可约时段为「未来 3 天 × 3 时段」的骨架实现，未做排班/容量精细管理。

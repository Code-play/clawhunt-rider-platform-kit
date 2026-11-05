# Web 前端（H5 求职者端 + 招聘专员工作台）

本目录是一个 **npm workspace**，包含两个可独立运行、可独立构建的 Vite + React 应用。
两个应用默认在**未连接后端时使用内置 mock**，可完全离线点通主流程；设置 `VITE_API_BASE` 后改为请求真后端，真后端不可用时自动回落 mock 并在控制台告警，不会白屏。

| 应用 | 目录 | 技术栈 | 对应订单任务 | 预览端口 |
| --- | --- | --- | --- | --- |
| H5 求职者端 | `web/h5` | React 18 + Vite 6 + 自绘移动端组件 | 任务 2/5（求职者端） | 4173 |
| 招聘专员工作台 / 驾驶舱 | `web/admin` | React 18 + Vite 6 + Ant Design 5 + dayjs | 任务 3/5 工作台 + 任务 4/5 驾驶舱示意 | 4174 |

> Node 版本要求：>= 20（实测 Node 24.13.0、npm 11.6.2）。
> Windows 下 PowerShell 执行策略会拦截 `npm.ps1`，请统一用 `cmd /c npm.cmd ...` 调用（下文命令均已按此写）。

---

## 1. 快速开始

```bat
cd web

:: 安装两个应用的依赖（workspace 一次装完）
cmd /c npm.cmd install

:: 构建两个应用（h5/dist + admin/dist）
cmd /c npm.cmd run build

:: 预览构建产物（两个端口同时可用）
cmd /c npm.cmd run preview:h5      :: http://127.0.0.1:4173
cmd /c npm.cmd run preview:admin   :: http://127.0.0.1:4174
```

开发模式（热更新）：

```bat
cmd /c npm.cmd run dev:h5      :: http://127.0.0.1:5173
cmd /c npm.cmd run dev:admin   :: http://127.0.0.1:5174
```

构建产物（2026-11-05 实测，`vite build` 一次通过）：

| 应用 | JS | CSS | gzip(JS) |
| --- | --- | --- | --- |
| `h5/dist` | 约 232 KB | 约 15 KB | 约 76 KB |
| `admin/dist` | 约 1.32 MB（Ant Design 全量，骨架可接受） | 约 9 KB | 约 419 KB |

两个应用的 `vite.config.js` 均使用 `base: './'`，`dist/` 可直接放到任意静态目录下打开；路由使用 `HashRouter`，无需服务端 rewrite。

---

## 2. mock 与真后端切换

### 2.1 默认（mock）

不设置 `VITE_API_BASE` 时，两个应用都走 `src/mock/` 里的内置 mock：

- 内存数据 + **700ms 延迟**（可用 `VITE_MOCK_LATENCY` 覆盖，便于冒烟测试）。
- H5 的 mock 数据会持久化到 `localStorage`（键 `rider.h5.mockdb`），刷新页面、断网恢复后会话/进度/预约都还在；「撤回授权并删除」或聊天页「重置演示数据」会一并清空。
- 管理端 mock 只存内存（刷新恢复初始演示数据），完整号码仅存在于 mock 内存中，查看需理由并写审计。
- H5 的 7 槽位对话是**确定性脚本**，并内置分支：政策问答、转人工、未成年 `end_minor`、资料收齐后站点推荐。
- 聊天页底部「演示工具（mock 模式）」提供：模拟断网 10 秒 / 立即恢复网络 / 重置演示数据 / 未成年分支，便于评委现场演示。

### 2.2 连接真后端

Vite 环境变量在**启动/构建时**读取，修改后需重新启动 dev 或重新 build。任选一种：

```bat
:: 方式 A：命令行临时注入（构建）
cmd /c "set VITE_API_BASE=http://127.0.0.1:8000&& npm.cmd run build:h5"
cmd /c "set VITE_API_BASE=http://127.0.0.1:8000&& npm.cmd run build:admin"

:: 方式 B：写入各应用的 .env.local（已提供 .env.example 模板）
:: web/h5/.env.local     -> VITE_API_BASE=http://127.0.0.1:8000
:: web/admin/.env.local  -> VITE_API_BASE=http://127.0.0.1:8000
```

行为约定：

- 请求路径统一为 `${VITE_API_BASE}/api/v1/...`；错误体按 `{code, message}` 解析。
- **4xx 业务错误**（未登录、缺理由、手机号格式错误等）原样抛给页面提示，不回落 mock。
- **网络错误 / 超时 / 5xx**：`console.warn` 后回落内置 mock，页面继续可用（不白屏）。
- 管理端登录成功后自动在请求头携带 `Authorization: Bearer <JWT>`；H5 若后端下发会话令牌，同样以 Bearer 方式携带。

### 2.3 前端使用的接口清单（契约 v1 + 扩展）

两个应用调用的是同一套 REST 语义；**下列路径如与后端实现不一致，只需改 `src/api/client.js` 一处**，页面与 mock 不受影响。

| 方法 | 路径 | 使用方 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/v1/consent` | H5 | 回传 `consent_version` + `consent_at` + `source_channel`，返回 `candidate_id` |
| POST | `/api/v1/agent/sessions` | H5 | 创建会话，返回 `session_id` |
| POST | `/api/v1/agent/sessions/{id}/messages` | H5 | `{text, client_message_id}` → `{reply, quick_replies, progress, actions}`；`client_message_id` 用于断网幂等重放 |
| GET / PATCH | `/api/v1/candidates/{id}` | 两端 | 档案读取 / 自助更正（H5 只传允许字段） |
| GET | `/api/v1/candidates/{id}/export` | H5 | 信息副本（JSON 下载） |
| POST | `/api/v1/candidates/{id}/revoke` | H5 | 撤回授权并删除 |
| GET | `/api/v1/stations`、`/api/v1/stations/{id}` | H5 | 站点、在招人数、可约时段 |
| POST | `/api/v1/bookings` | H5 | `{candidate_id, station_id, slot_start}` 创建预约 |
| GET / PATCH | `/api/v1/bookings/{id}` | H5 | 预约详情 / 改约（`slot_start`） |
| POST | `/api/v1/bookings/{id}/cancel` | H5 | 取消预约 |
| POST | `/api/v1/auth/login` | admin | 工号 + 密码 → `{token, user{name, employee_no}}` |
| GET | `/api/v1/admin/candidates` | admin | 列表查询：`q/status/source_channel/station_id/intent_level/page/page_size` |
| GET / PATCH | `/api/v1/admin/candidates/{id}` | admin | 详情 / 更正（`{fields, reason}`，reason 必填） |
| POST | `/api/v1/admin/candidates/{id}/actions` | admin | `confirm_interview`（需 `slot_start`）/ `handoff` / `reject`，`reason` 必填 |
| POST | `/api/v1/vault/detokenize` | admin | `{token, reason}` → 完整号码（只展示一次） |
| POST | `/api/v1/vault/tokenize` | 两端 | `{type, value}` → `{token}` |
| GET | `/api/v1/admin/interviews?from=&to=` | admin | 面试日程（日/周视图数据） |
| GET | `/api/v1/admin/stations`、PATCH `/api/v1/admin/stations/{id}` | admin | 站点列表 / 调整在招名额（`open_quota`） |
| GET | `/api/v1/admin/metrics` | admin | 驾驶舱 7 个 KPI、漏斗、渠道分布 |

**为前端演示补充的扩展字段（后端可逐步补齐；前端全部做了缺失兜底，不会因缺字段报错）：**

- 候选人：`name_masked`、`phone_masked`（契约只有 token；H5 只展示掩码，管理端列表也用掩码）。
- 会话创建响应：`greeting`（首条 AI 问候 + 快捷选项 + 初始 progress；缺失时 H5 用本地兜底文案，也兼容后端把问候放在 `reply` 字段）。
- 消息响应：`message_id`（前端去重）、`policy_card{doc_id,title,version,effective_date,answer,disclaimer}` + `source_label`（政策卡出处）、`stations[]`（资料收齐后推荐站点）。
- 站点：`booked_count`、`manager_virtual_no` / `manager_display_no`（站长虚拟号，H5 用 `tel:` 拨号）。
- 候选人详情（admin）：`qualification{level,score,rules[],suggestion}`、`conversation_summary`、`conversation_key_points[]`、`transcript[]`、`audit_log[]`、`interview_slots[]`、`interviews[]`。
- 管理端列表/详情：`intent_level`（1-5 意向度）、`station_name`。

> **回落是「粘性」的**：一旦真后端出现 404（契约接口未实现）、网络错误或 5xx，本轮会话后续请求**整体**改用内置 mock（`console.warn` 提示），避免真/假数据混用导致页面自相矛盾；刷新页面后重新尝试真后端。

### 2.4 与 `docs/backend.md` 的路径差异（联调前需对齐）

本仓库后端切片按自己的路由实现，与前端当前采用的契约 v1 路径并非逐项一致。默认 mock 验收不受影响；若要把 `VITE_API_BASE` 指向 `backend/`，需按下表对齐（或后端补齐左侧路径），差异出现时前端会整体回落 mock 以保证不白屏：

| 能力 | 前端（`docs/web.md` / 契约 v1） | 后端切片（`docs/backend.md`） |
| --- | --- | --- |
| 员工登录 | `POST /auth/login` → `{token,user}` | `POST /auth/token` → `{access_token,...}` |
| 告知同意建档 | `POST /consent` | 无该端点；建档为 `POST /candidates` |
| 候选人列表 | `GET /admin/candidates` | `GET /candidates`（`limit/offset` 分页） |
| 档案更正 | `PATCH /admin/candidates/{id}` `{fields,reason}` | `PATCH /candidates/{id}` |
| 面试动作 | `POST /admin/candidates/{id}/actions` | `POST /candidates/{id}/status`（状态机） |
| 面试日程 | `GET /admin/interviews` | 无独立端点（预约见 `GET /bookings`） |
| 站点名额 | `GET /admin/stations` + `PATCH /admin/stations/{id}` | `GET /stations`（名额随预约扣减） |
| 驾驶舱指标 | `GET /admin/metrics`（7 KPI + 漏斗 + 渠道） | `GET /kpi/summary`（视图 8 列） |
| 政策卡 | 跟随会话消息的 `policy_card` 扩展 | `GET /policies/search?q=`（带文档名+版本） |
| 保险箱 | `POST /vault/tokenize`、`POST /vault/detokenize` | 一致（detokenize 需权限 + reason） |

联调时的最小改法：只改两个 `src/api/client.js` 的路径与响应字段映射（页面、mock、类型结构均不受影响）。

---

## 3. H5 求职者端：已实现页面与验收路径

### 3.1 页面清单

| 路由 | 页面 | 要点 |
| --- | --- | --- |
| `#/` | 渠道入口 | 读取 URL `?source_channel=xxx` 并展示渠道名；开始登记 / 继续登记 / 重新开始 |
| `#/consent` | 告知同意 | 一屏说明收集/不收集/用途/保存期限/权利；**不勾选无法开始**；不同意有「电话咨询」出口；同意后回传版本 + 时间戳 |
| `#/chat` | AI 对话 | 气泡、快捷选项、7 槽位进度条、转人工、政策回答卡、站点推荐卡、断网排队与幂等重放 |
| `#/stations` | 附近站点 | 距离 / 在招人数 / 可约时段，选时段预约；改约入口 `?reschedule=bookingId` |
| `#/result/:bookingId` | 预约结果 | 单号、站点、时段、高德导航、站长虚拟号 `tel:`、到站须知、改约 / 取消 |
| `#/me` | 我的信息（自助四项） | 查看/更正、下载副本、撤回授权并删除、联系人工；展示同意版本与时间 |
| 全局 | AI 身份标识 | 每屏固定底栏「本服务由 AI 提供 · 可随时转人工」+ 一键转人工（`AiFooter` 单点实现） |
| 全局 | 断网提示 | 顶栏下方提示离线/重发状态；输入区显示排队条数 |

### 3.2 验收路径（对应订单验收 1-6 条）

1. **渠道入口**：打开 `http://127.0.0.1:4173/?source_channel=wechat`，页面显示「渠道来源：微信好友分享」与 `?source_channel=wechat`。
   > 注意：`source_channel` 必须放在 hash 之前（`...?source_channel=wechat#/chat`）；进入子路由后参数仍在地址栏。
2. **告知同意闸门**：点「开始登记」，未勾选时按钮为「请先勾选同意」且禁用；点「我不同意」出现电话咨询 `tel:` 出口；勾选后提交，`localStorage` 中可见 `consent_version` 与 `consent_at`。
3. **7 槽位对话**：依次点快捷选项（姓名 → 手机号 → 出生年月 → 跑单区域 → 工作类型 → 电动车 → 可到岗时间），进度从 `0/7` 走到 `7/7`，字段 chips 逐个打勾；资料收齐后自动推送 3 个站点推荐卡。
   - 政策问答：点「政策问答」或输入含「保险/结算/入职/隐私」的问题，返回**政策回答卡**，卡内显示 `出处：《文档名》 版本（生效日期）` + **免责声明**。
   - 转人工：点工具栏「转人工」或直接输入「转人工」，返回 handoff 提示并展示热线。
   - 未成年分支：打开「演示工具 → 未成年分支」，返回 `end_minor` 文案，输入框与发送按钮禁用（出生年月填 `2010-01` 也会触发同一分支）。
4. **断网 10 秒恢复**：打开「演示工具 → 模拟断网 10 秒」，发消息 → 出现「有 1 条消息在本地排队」+ 用户气泡「待发送」；约 10 秒后自动恢复并重发，AI 回复出现、排队归零、进度保持 `7/7`、`localStorage` 里消息数与进度不变。真实网络断开时同样生效（监听 `online/offline` + 3 秒轮询兜底）。
5. **站点推荐 → 预约 → 结果**：推荐卡展示距离、在招人数、可约时段；选时段 →「预约这个时段」→ 结果页。结果页含高德导航按钮、站长虚拟号 `tel:4000001234`、4 条到站须知、改约与取消（取消有二次确认）。
6. **个人信息自助四项**：右上角「我的信息」→ 查看/更正（保存后显示更新值）、下载 JSON 副本、撤回授权并删除（二次确认后清空后端 mock 记录 + 本地 `rider.h5.*` 缓存并回首页）、联系人工（热线 + 在线转人工）。
7. **适配**：375 / 390 / 414 宽度无横向溢出，AI 底栏常驻、输入框紧贴底栏上方；把根字号放大到 150%（`html{font-size:24px}`）后无溢出、不遮挡（底栏高度由 `ResizeObserver` 实测写入 CSS 变量，输入框自适应上移）。

### 3.3 关键实现说明

- **断网不丢会话/进度**：`session_id`、`messages`、`progress`、`outbox` 全部写 `localStorage`；离线时消息进 outbox（含客户端消息 id），恢复网络后按顺序重放；mock 以后端视角用 `client_message_id` 幂等去重，重复提交不会重复推进槽位或重复入库。
- **敏感信息**：H5 只展示掩码（`张*` / `138****8000`）；姓名/手机号在 mock 后端以 token 存储；自助更正时前端不缓存完整值。
- **AI 标识**：只在 `components/AppLayout.jsx` + `components/ui.jsx` 的 `AiFooter` 实现一次，所有页面共享，避免逐页复制。

---

## 4. 招聘专员工作台（admin）：已实现页面与验收路径

### 4.1 页面清单

| 路由 | 页面 | 要点 |
| --- | --- | --- |
| `#/`（未登录） | 登录 | 工号 + 密码（演示账号预填 `A1024 / 123456`），成功后 Bearer JWT 存 `sessionStorage` |
| `#/dashboard` | 指标看板（驾驶舱示意） | **7 个 KPI** 卡片（含环比与迷你趋势条）、线索转化漏斗、渠道来源分布，数据来自 mock |
| `#/candidates` | 我的候选人 | 列表默认手机号掩码；按姓名/手机号/站点搜索 + 状态/来源/站点/意向度筛选 + 分页 |
| `#/candidates/:id` | 候选人详情 | AI 建档字段可更正（修改原因必填、逐字段留痕）、资格初筛建议、对话摘要与完整转写、确认面试/转人工/标记不合适（理由必填）、查看完整手机号（理由必填、只显示一次） |
| `#/schedule` | 面试日程 | 自绘周视图网格（7 天 × 09:00-18:00）+ 日视图列表，可切换日期/站点，点击面试块进候选人详情 |
| `#/stations` | 站点与名额管理 | 在招/已约/剩余名额、剩余进度条、满员状态、按站点调整在招名额（实时生效） |
| 全局 | 页面个人水印 | 姓名 · 工号 · 日期，`position:fixed` 覆盖层 + SVG 平铺，`pointer-events:none` |

### 4.2 验收路径

1. 打开 `http://127.0.0.1:4174/`，登录（已预填 `A1024 / 123456`）→ 进入驾驶舱，可见 7 个 KPI、漏斗、渠道分布。
2. 「我的候选人」：列表手机号均为 `138****80xx` 形式；任意筛选（如状态=已预约）后列表与总数同步变化。
3. 点任意候选人进入详情：
   - 修改任意字段并直接点「保存更正」→ 提示「必须填写修改原因」；填写原因后保存 → 右侧「操作记录与修改留痕」新增一条「改前 → 改后 + 操作人 + 时间 + 理由」。
   - 「查看完整手机号」→ 弹窗要求填写理由（少于 4 字不通过）→ 提交后显示完整号码与审计编号；关闭弹窗后 DOM 中不再存在该号码，`localStorage` / `sessionStorage` 均无完整号码（已实测）。
   - 「标记不合适」不填理由 → 表单校验拦截；填写后提交 → 状态变为「已结束」且留痕新增操作记录。
   - 「确认面试」需同时选面试时段与填理由 → 提交后状态变「已预约」、「面试安排」时间线新增记录（同时计入站点已约人数）。
4. 「面试日程」：周视图 7 列 × 10 行网格显示面试块（待面试/已到访/未到访颜色区分），切换「日视图」显示当天时间线。
5. 「站点与名额」：表格展示在招/已约/剩余；点「调整名额」改数并保存 → 表格、顶部统计、剩余进度条同步更新。
6. 任意页面均可见水印「张敏 · A1024 · 当日日期」（右上角下拉可退出登录）。

### 4.3 安全/合规实现要点

- 列表与详情默认只显示掩码；完整手机号只在**填写理由**后调用 `/vault/detokenize`，响应只保存在弹窗组件 state 中，弹窗关闭即销毁；不写 `localStorage` / `sessionStorage` / URL，不做前端缓存。
- 更正与三类操作全部要求理由，且 mock 后端同样做 422 校验（前端校验之外的第二道）。
- 水印为全局覆盖层，不影响点击；退出登录清除 `sessionStorage` 中的 token 与水印身份。

---

## 5. 目录结构

```text
web/
├── package.json               # npm workspace（h5 + admin）
├── h5/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx / App.jsx / styles.css
│       ├── api/client.js      # mock/真后端切换、断网判定、业务 API
│       ├── components/        # AppLayout（AI 底栏）、ui.jsx（进度/政策卡/站点卡/弹窗）、Toast
│       ├── lib/               # storage、format 掩码/时间、network 状态
│       ├── mock/              # data 静态数据、conversation 7 槽位脚本、index mock 后端
│       ├── pages/             # Entry / Consent / Chat / Stations / Result / SelfService
│       └── state/RiderContext.jsx
└── admin/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx / App.jsx / styles.css
        ├── api/client.js      # Bearer JWT、mock 回落、业务 API
        ├── components/        # AppLayout、Watermark、DetokenizeModal
        ├── lib/utils.js       # 掩码、状态/来源字典、时间格式
        ├── mock/index.js      # 候选人/站点/日程/指标 mock 后端 + vault
        ├── pages/             # Login / Dashboard / Candidates / CandidateDetail / Schedule / Stations
        └── state/AuthContext.jsx
```

---

## 6. 未做项与已知限制（骨架交付）

- **管理端 mock 不持久化**：刷新页面会恢复初始演示数据；H5 的 mock 数据持久化（断网/刷新验收需要）。
- **驾驶舱为静态示意**：7 个 KPI 与漏斗/渠道为 mock 静态数据，未接真实埋点/数仓。
- **鉴权为演示级**：仅「登录 → Bearer token → 接口带 Authorization」链路；未做刷新 token、RBAC 权限、工号体系对接。
- **与后端切片端点未逐一对齐**：见 2.4 差异表；前端按契约 v1 实现，联调前需对齐路径/字段，或由后端补齐契约路径。默认 mock 模式不受影响。
- **地图为外链**：导航跳高德 Web URI，未集成地图 SDK / 嵌入地图组件。
- **信息副本仅 JSON**：未做 PDF/图片导出；未做 OCR、证件上传（与「不收集证件号」的告知一致）。
- **未做 i18n / 深色模式**：仅简体中文、浅色主题。
- **自动化测试**：未接入 Playwright/Vitest 用例；本次用无头浏览器脚本对 H5 与 admin 主流程做了冒烟（渠道、同意、7 槽位、政策卡、断网重放、预约、结果页、自助四项、登录、掩码列表、留痕、detokenize、日程、名额、水印、375/390/414 + 150% 字体）。
- **构建体积**：admin 因 Ant Design 全量打包约 1.32 MB（gzip 419 KB），骨架阶段可接受；后续可按需引入或路由分包。

---

## 7. 依赖与许可证

全部为 MIT 许可，无 GPL/AGPL：

`react`、`react-dom`、`react-router-dom`、`vite`、`@vitejs/plugin-react`、`antd`、`@ant-design/icons`、`dayjs`。

生产依赖仅 6 个（h5 3 个、admin 6 个），其余为构建/devDependencies；无私有源、无本地路径依赖。

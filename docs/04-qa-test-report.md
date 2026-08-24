# QA 测试报告 — WMS QuickStart v0.1.0

## 2026-04-29 多模型全面回归与线上页面巡检

**测试环境**: 生产环境 `app.maxsmartwms.online` + `api.maxsmartwms.online`  
**后端版本**: `0a153cc8b49273744b7890a80d8de10d0979dfd5`  
**测试方法**: 多模型评审先拆分为后端完整性、前端页面/设置、WMS 流程专家三条线；随后本地回归、生产 API 闭环、生产浏览器闭环、全页面桌面/手机排版巡检。

### 结论

- 后端完整性修复完成：packing 校验现在要求所有已拣货 SKU 都被扫描匹配，少扫一个 SKU 不会再进入 `packed`。
- 本地回归通过：`backend/.venv/bin/pytest` -> `123 passed`；`frontend npm run build` 通过；`npm run lint -- --quiet` 通过。
- 生产 API 闭环通过：pack-before-pick 返回 `409`；partial pack 返回 `verified=false`；完整 pack 后可 ship，最终 shipment summary 为 `shipped`。
- 生产 Receiving -> Putaway 浏览器闭环通过：进入 live receiving、扫码、确认收货、生成内部标签、complete receiving、产生 putaway task、完成 putaway。
- 生产 Shipping 浏览器闭环通过：页面显示 pack/ship action；确认包装、录入 carrier/tracking、确认发运后，订单与 summary 均为 `shipped`。
- 全页面线上巡检通过：公开页、租户运营页、设置页、客户门户、平台用户/工作区，共 `70` 个页面/视口组合；失败 `0`，console error `0`。

### 多模型测试方案落点

- **后端/数据完整性**：Receiving、Putaway、Picking、Shipping 的状态推进必须由前一阶段真实完成触发；扫描、拣货、打包、发运都要验证“缺项不能推进”。
- **前端/页面合理性**：重点检查 `/receiving`、`/putaway`、`/picking`、`/shipping`、`/inventory`、`/users`、`/workspaces`、设置页和 portal 页在桌面/手机视口下是否空白、溢出、遮挡或报错。
- **WMS 流程专家视角**：每个阶段只暴露应处理的状态订单；异常订单应被收住在当前环节，不能通过跳步让下游承接脏数据。

### 测试账号策略

- 线上 smoke/regression 脚本不再依赖公开注册邮件链路。
- 有 `WMS_AUDIT_PLATFORM_EMAIL` / `WMS_AUDIT_PLATFORM_PASSWORD` 时，脚本会调用受保护的 `/maintenance/test-tenant/bootstrap`，直接创建“已验证邮箱 + active subscription”的临时测试租户。
- 没有平台管理员凭证时，脚本才回退到 `/subscriptions/register`，这个模式仅适合本地或关闭邮件验证的环境。

### 新增验证脚本

- `frontend/scripts/verify-pack-completeness.mjs`
  - 验证 pack-before-pick、partial pack、complete pack、ship confirm。
- `frontend/scripts/audit-production-pages.mjs`
  - 验证公开页、租户页、portal 页、平台页的桌面/手机排版、500 响应、空白页、页面级横向溢出和 console error。
- 现有 `verify-receiving-putaway-action-surfaces.mjs` 与 `verify-shipping-flow.mjs` 使用平台管理员维护接口创建已验证临时测试租户，避免注册邮件链路故障阻塞 WMS 业务流测试。

### 线上实测记录

```bash
cd backend
.venv/bin/pytest

cd ../frontend
npm run build
npm run lint -- --quiet
WMS_AUDIT_PLATFORM_EMAIL=... WMS_AUDIT_PLATFORM_PASSWORD=... npm run smoke:pack-completeness
WMS_AUDIT_PLATFORM_EMAIL=... WMS_AUDIT_PLATFORM_PASSWORD=... npm run smoke:receiving-putaway
WMS_AUDIT_PLATFORM_EMAIL=... WMS_AUDIT_PLATFORM_PASSWORD=... node ./scripts/verify-shipping-flow.mjs
WMS_AUDIT_PLATFORM_EMAIL=... WMS_AUDIT_PLATFORM_PASSWORD=... npm run audit:production-pages
```

关键输出：

- `smoke:pack-completeness`: `partialVerified=false`, `completeVerified=true`, `finalStatus=shipped`
- `smoke:receiving-putaway`: `INB-ACT-139598` 完成收货与 putaway task
- `verify-shipping-flow`: `shippedStatus=shipped`, `summaryStatus=shipped`
- `audit:production-pages`: `checkedPages=70`, `failures=0`, `consoleErrorCount=0`

### 备注

- 自助注册当前被邮件验证发送失败拦住，测试脚本已改用平台管理员创建临时测试账号的后备路径；注册邮件链路应作为单独邮件服务任务继续处理。
- 手机端若页面内存在数据表格，巡检会记录表格内部宽度，但页面级 `overflowX=0`，未发现整页横向撑破或 CTA 遮挡。
- 线上测试结束后，已禁用 `pack*`、`ship*`、`act*`、`layout*` 这些 `example.com` 临时测试用户，避免继续污染用户管理界面；测试订单和库存记录保留为审计证据。

---

## 2026-04-29 生产闭环回归补充

**测试环境**: 生产环境 `app.maxsmartwms.online` + `api.maxsmartwms.online`
**测试范围**: Receiving -> Putaway 主流程、异常流、前端提示、API 数据一致性
**测试批次**: QA 前缀订单，run id `qa0429064310`

### 结论

- 正常流程通过：收货到暂存、空库位上架、同 SKU 合并、拆分上架均能闭环。
- 异常流程通过：未知 barcode 不推进订单状态；缺少暂存位置不能上架；不同 SKU 库位默认阻止确认；不同 lot/expiry 可提示后按业务规则处理。
- 页面回退和状态一致性通过：前端阻止操作后，API 中订单、任务、库存记录保持原状态。
- 线上浏览器回归通过：Receiving blocker、手工扫码错误提示、Putaway destination warning 均已在生产域名验证。
- 浏览器 console error：`0`。

### 本次发现并修复的问题

- Receiving 详情页曾在仍有 `Expected > Received` 的 SKU 数量时显示类似已完成的提示；现已改为按未接收 SKU units 判断。
- 手工输入 barcode 失败时，页面曾只显示笼统失败；现已显示尝试输入的 code 和后端拒绝原因。
- Putaway 的目标库位冲突提示曾藏在折叠面板内；现已提前展示在确认按钮附近，并在不同 SKU 冲突时禁用确认。

### 验证命令

```bash
cd frontend
npm run build
npm run smoke:receiving-package-fallback
npm run lint
```

`npm run lint` 当前退出成功，但仍有历史遗留 unused-symbol warning；这些 warning 不属于本次阻塞项，建议作为单独清理任务处理。

### 生产发布记录

- 前端提交：`31641e1 Improve receiving and putaway exception feedback`
- Vercel deployment：`dpl_GywWdFiLKAHEqYgpVmeEzoQXhNPE`
- 生产域名：`https://app.maxsmartwms.online`

---

**测试日期**: 2026-04-06
**测试环境**: 本地 (Python 3.13 + SQLite + Serveo公网隧道)
**测试人员**: Claude QA
**代码版本**: commit 0874c1b (126文件, 17,442行)

---

## 测试结果总览

| 类别 | 通过 | 失败 | 警告 | 通过率 |
|------|:---:|:---:|:---:|:---:|
| 健康检查 | 1 | 0 | 0 | 100% |
| 公开端点 | 3 | 0 | 0 | 100% |
| 注册流程 | 2 | 0 | 0 | 100% |
| 认证安全 | 3 | 0 | 1 | 75% |
| 订阅强制 | 2 | 0 | 0 | 100% |
| WMS操作 | 12 | 0 | 0 | 100% |
| 客户门户 | 3 | 0 | 0 | 100% |
| **跨租户隔离** | **0** | **2** | **0** | **0%** 🔴 |
| 套餐限额 | 2 | 0 | 0 | 100% |
| 前端页面 | 4 | 0 | 0 | 100% |
| 调研表 | 1 | 0 | 0 | 100% |
| 集成 | 1 | 0 | 0 | 100% |
| **合计** | **34** | **2** | **1** | **92%** |

---

## 🔴 严重Bug（必须立即修复）

### BUG-001: 跨租户数据泄露 [CRITICAL]

**严重程度**: P0 — 数据安全漏洞
**影响**: 任何租户可以看到所有其他租户的数据

**复现步骤**:
1. 注册一个新租户 "QA Test Corp"
2. 用新租户的 JWT 调用 `GET /api/v1/inventory/`
3. 预期结果：返回 0 条记录（新租户没有库存）
4. 实际结果：**返回了 6 条记录（属于 DFW Logistics 的数据）**

**根因**: 当前使用 SQLite 开发数据库，SQLite 不支持 PostgreSQL 的 Row-Level Security (RLS)。`database.py` 中虽然有 `_is_sqlite` 判断跳过了 RLS SET 命令，但**没有在应用层做 tenant_id 过滤**。所有查询直接返回全部数据。

**影响范围**: 所有带 tenant_id 的表 — inventory, clients, warehouses, orders, skus, tasks, billing 全部泄露。

**修复方案**:
- 方案A: 在 SQLite 模式下，为每个查询自动注入 `WHERE tenant_id = ?` 过滤（通过 SQLAlchemy event listener）
- 方案B: 本地开发也使用 Docker PostgreSQL + 真正的 RLS
- 方案C: 在每个 Service/Endpoint 中显式加 `tenant_id` 过滤（已在部分端点实现，但不完整）

**建议**: 方案A（全局过滤器）是最安全的，即使忘记写 WHERE 也不会泄露。

---

## 🟡 中等问题

### BUG-002: .env 中的 SMTP 密码已提交到 Git [MEDIUM]

**文件**: `backend/.env`
**内容**: `SMTP_PASSWORD=<redacted Gmail App Password>`

**影响**: 虽然仓库是 Private，但如果泄露或未来转 Public，Gmail App Password 会被暴露。

**修复**:
1. 在 `.gitignore` 中加入 `backend/.env`（已有，但文件是在 gitignore 之前 commit 的）
2. `git rm --cached backend/.env` 从历史中移除
3. 旋转 Gmail App Password

### BUG-003: SQLite 数据库文件提交到 Git [MEDIUM]

**文件**: `backend/wms_dev.db`
**影响**: 测试数据和用户密码哈希被提交

**修复**: `git rm --cached backend/wms_dev.db` + 在 `.gitignore` 加 `*.db`

### BUG-004: `subscriptions.py` 中使用 `__import__` hack [LOW]

**文件**: `backend/app/api/v1/endpoints/subscriptions.py` L96-99
**代码**: `__import__("sqlalchemy").select(...)` + `__import__("app.models.subscription", ...)`
**影响**: 代码可读性差，IDE 无法检测错误
**修复**: 改为正常 import

### BUG-005: CORS 配置为 `allow_origins=["*"]` [MEDIUM]

**文件**: `backend/app/main.py` L45
**影响**: 任何网站都可以向 API 发请求（CSRF风险）
**修复**: 生产环境改为白名单

### BUG-006: 订阅缓存无 TTL [LOW]

**文件**: `backend/app/core/deps.py` L23
**影响**: 订阅过期后，缓存中仍然是 "allowed"，直到重启服务才更新
**修复**: 加 TTL（5分钟过期），或使用 Redis 缓存

---

## ⚠️ 警告

### WARN-001: 未认证请求返回 401 而非 403

**预期**: 无 token 访问 API 返回 `403 Forbidden`
**实际**: 返回 `401 Unauthorized`
**影响**: 低，不影响功能。HTTP 语义上 401 更准确（没有提供认证凭证）

---

## ✅ 通过的测试（亮点）

1. **注册流程完整**: 注册 → 创建租户 + 用户 + 试用订阅 → 返回 JWT → 即时可用
2. **重复注册防护**: 相同公司代码或邮箱注册返回 400
3. **密码安全**: 错误密码返回 401，无泄露信息
4. **JWT 验证**: 无效 token 返回 401
5. **套餐限额生效**: Starter 只能创建 1 个仓库，第 2 个返回 403 + 升级提示
6. **所有 WMS 操作端点正常**: inventory/orders/clients/warehouses/skus/tasks/billing/portal/agv 全部 200
7. **客户角色隔离**: client_viewer 只能访问 portal 端点
8. **前端页面全部可访问**: /, /login, /register, /survey.html
9. **调研表提交 + 邮件发送**: 正常工作

---

## 代码质量审计

| 项目 | 状态 | 说明 |
|------|:---:|------|
| .env 不在 git 中 | ✅ | .gitignore 已配置 |
| SQL 注入风险 | ✅ | 全部使用 SQLAlchemy ORM，无原始 SQL 拼接 |
| 密码哈希 | ✅ | bcrypt 哈希存储 |
| JWT 过期时间 | ✅ | 8 小时（适合仓库班次） |
| 结构化日志 | ✅ | JSON 格式 + request_id + tenant_id |
| 速率限制 | ✅ | 200 req/min（内存版） |
| CORS | ⚠️ | 当前 `*` 开放，生产需改白名单 |
| Terraform IaC | ✅ | VPC/ECS/RDS/Redis/S3 完整 |
| CI/CD | ✅ | GitHub Actions lint+test+deploy |
| 单元测试 | ✅ | 端到端流程 + 计费测试 |
| 敏感数据 | ⚠️ | .env 和 .db 需从 git 历史清除 |

---

## 建议优先修复顺序

| 优先级 | Bug ID | 预计耗时 | 修复方案 |
|:---:|--------|:---:|------|
| **P0** | BUG-001 跨租户泄露 | 30分钟 | SQLAlchemy 全局 event listener 注入 tenant_id 过滤 |
| **P1** | BUG-002 密码泄露 | 5分钟 | git rm --cached .env + 旋转密码 |
| **P1** | BUG-003 DB泄露 | 5分钟 | git rm --cached *.db + 更新 gitignore |
| **P2** | BUG-005 CORS | 2分钟 | 恢复白名单配置 |
| **P3** | BUG-006 缓存TTL | 10分钟 | 加 timestamp 字段 + 5分钟过期 |
| **P3** | BUG-004 import hack | 5分钟 | 改为正常 import |

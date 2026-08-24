# QA 测试报告 — WMS QuickStart v0.1.0

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
**内容**: `SMTP_PASSWORD=[REDACTED]`

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

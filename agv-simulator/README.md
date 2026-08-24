# AGV Local Simulator

本目录是独立的本地 AGV 模拟器，不依赖 WCS adapter 后端代码。

## 运行

```bash
cd /Volumes/MaxRelocated/WMS/agv-simulator
npm start
```

打开浏览器访问：

```text
http://localhost:4179
```

如需换端口：

```bash
AGV_SIM_PORT=4188 npm start
```

## 功能

- 展示仓库地图、地面库位、货架区、dock doors、AGV 路线、等待点、充电点和安全区。
- 地图画布支持滚动与全屏查看，便于检查 L 形仓库和右侧 dock corridor。
- 实时展示 AGV 当前位置、任务进度、当前步骤和速度。
- 记录操作日志。
- 提供 Dallas layout + `wcs_point_mapping_draft` 固定样例：`GET /api/layouts/dallas`。
- 自动按任务进度模拟 WCS `stepStatus=20/30` 回调；异常使用 `Fail` 或 `/api/tasks/{id}/fail` 触发 `stepStatus=40`。
- 本地回调接口：`POST /api/wcs/step-status`。
- WCS-style 任务入口：`POST /api/wcs/transport-task`。
- WCS 供应商兼容任务入口：`POST /task/wlTaskInfo/addTransportTask`。
- WCS 供应商兼容 ready 接口：`POST /task/wlReadyAgvRobot/editReadyConfig`。
- WCS 供应商兼容 QC 接口：`POST /QualityComplete`。
- WCS 供应商兼容登录接口：`POST /loginToken`。
- 已接收回调查询：`GET /api/wcs/callbacks`。
- 已保存交换查询与回放：`GET /api/exchanges`、`POST /api/exchanges/{id}/replay`。

## 模拟 stepStatus

点击页面右上角 `Start` 后，模拟器会在约 12 秒内依次触发：

- `20`：到达取货点
- `30`：任务完成
- `40`：异常，仅在点击 `Fail` 或调用 fail API 时触发

每次触发都会在页面右侧显示 payload，并 POST 到本地 mock endpoint。

## WCS-style 任务入口

```bash
curl -s -X POST http://localhost:4179/api/wcs/transport-task \
  -H 'content-type: application/json' \
  -d '{
    "wtaskinfoType": "AGV搬运",
    "startPos": "INB-01",
    "endPos": "SHP-04",
    "wtaskinfoPsn": "PALLET-001",
    "wtaskinfoReturnurl": "http://localhost:4179/api/wcs/step-status"
  }'
```

供应商兼容路径用于 WMS live sandbox dispatch：

```bash
curl -s -X POST http://localhost:4179/task/wlTaskInfo/addTransportTask \
  -H 'content-type: application/json' \
  -H 'token: sim-token' \
  -d '{
    "wtaskinfoType": "AGV搬运",
    "startPos": "DAL-DOCK-DOCK-27",
    "endPos": "DAL-STO-DAL-A-01-01-01-01",
    "wtaskinfoPsn": "DAL-SANDBOX-001",
    "wtaskinfoReturnurl": "https://api.maxsmartwms.online/api/v1/integrations/wcs/webhook/TENANT-ID/taskfinish",
    "wtaskinfoScode": "DAL",
    "wtaskinfoPalletSpec": "GMA"
  }'
```

## Dallas layout + WCS point mapping draft 联调

固定样例文件：

```text
agv-simulator/fixtures/dallas-layout-wcs-point-mapping-draft.json
```

该文件记录 Dallas AGV standard layout v2。WCS point mapping draft 会由模拟器
按布局动态生成：

- `DAL-A/B/C` 是按客户货物尺寸规划的超尺寸地面库位。A 货物为
  68 x 58 x 100 in，按 6ft x 5ft x 9ft 库位规划，A 区因左侧封闭
  让出 12ft 作为内部 AGV 连接通道后剩余 28ft x 22ft，排布 4x4 共
  16 个库位；B/C 货物为 104 x 55 x 98 in，按 9ft x 5ft x 9ft 库位
  规划，各 40ft x 22ft，排布 4x4 共 16 个库位；A/B/C 合计 48 个
  floor-storage points；
- ABC 横向尺寸仍保持原图 120ft：A-CONN 12ft + A 28ft + B 40ft
  + C 40ft；rack 到 ABC 的 34ft 纵向尺寸分配为上方 AGV 车道 12ft
  + 囤货深度 22ft；
- A/B/C 画布按真实区域面积、货物 footprint、库位尺寸、剩余边带
  和容量变化绘制；
- AGV 不进入 A/B/C 绿色囤货库位内部，A 区通过 `A-CONN` 内部通道
  连接上方过道和下方 lane，B/C 使用外侧边缘交接点；
- `ABC-LOWER` 是 A/B/C 下方的非库位 AGV 行驶区域，可作为受控回程/通行 lane，
  且不占用 A/B/C 原有 34ft rack-to-ABC 尺寸；
- `DAL-RACK` 是靠 office 的唯一 4 层货架区，共 60 个 storage points；
  货架按 15 个 8ft bay、4 层规划，单层净高 65in，深度按 GMA 托盘
  深度 40in/3.33ft 标识；
- `DOCK-23` 到 `DOCK-30` 是 8 个 external dock points，不是 WMS storage locations；
- `WAIT-TOP`、`WAIT-DOCK`、`CHG-01` 是 AGV buffer/station points；
- 当前 `/api/layouts/dallas` 返回 119 个 WCS draft points。

模拟器暴露布局和草稿：

```bash
curl -s http://localhost:4179/api/layouts/dallas
```

一键 smoke 会自启动模拟器，验证 health、读取 Dallas mapping draft、创建 WCS-style transport task、生成 route/state，覆盖 pause/resume/reset/complete/fail，并验证 exchange replay：

```bash
cd /Volumes/MaxRelocated/WMS/agv-simulator
npm run smoke:dallas
```

客户审阅版图纸可以从同一份 Dallas layout 数据生成。该命令会导出主布局
和货架详图的 HTML、PNG、PDF：

```bash
cd /Volumes/MaxRelocated/WMS/agv-simulator
npm run review:dallas
```

手动流程：

```bash
cd /Volumes/MaxRelocated/WMS/agv-simulator
AGV_SIM_PORT=4179 npm start
```

```bash
curl -s http://localhost:4179/api/health
curl -s http://localhost:4179/api/layouts/dallas
curl -s -X POST http://localhost:4179/api/wcs/transport-task \
  -H 'content-type: application/json' \
  -d '{
    "wtaskinfoType": "AGV搬运",
    "startPos": "DAL-DOCK-DOCK-27",
    "endPos": "DAL-STO-DAL-A-01-01-01-01",
    "wtaskinfoPsn": "DAL-MANUAL-001",
    "wtaskinfoReturnurl": "http://localhost:4179/api/wcs/step-status",
    "wtaskinfoScode": "DAL",
    "wtaskinfoPalletSpec": "GMA"
  }'
curl -s http://localhost:4179/api/state
curl -s -X POST http://localhost:4179/api/tasks/TASK_ID/start
curl -s -X POST http://localhost:4179/api/tasks/TASK_ID/pause
curl -s -X POST http://localhost:4179/api/tasks/TASK_ID/resume
curl -s -X POST http://localhost:4179/api/tasks/TASK_ID/complete
curl -s http://localhost:4179/api/wcs/callbacks
curl -s http://localhost:4179/api/exchanges
curl -s -X POST http://localhost:4179/api/exchanges/EXCHANGE_ID/replay -H 'content-type: application/json' -d '{"latest_only":true}'
```

把 `TASK_ID` 替换成创建任务返回的 `data.wtaskinfoTid`。路线首尾应分别是 `DAL-DOCK-DOCK-27` 与 `DAL-STO-DAL-A-01-01-01-01`；回调 payload 的 `stepStartpos` / `stepEndpos` 使用同一组 WCS point code。

## Render 公网 sandbox

仓库根目录的 `render.yaml` 已包含 `wms-agv-sandbox` service，rootDir 为
`agv-simulator`，健康检查为 `/api/health`。部署完成后，把 Dallas WCS
`base_url` 配成 Render 服务 URL，然后先跑：

```bash
WMS_TOKEN=... node tools/wms.mjs wcs config update --dry-run --warehouse-id WH-ID --base-url https://wms-agv-sandbox.onrender.com --callback-url CALLBACK-URL
WMS_TOKEN=... node tools/wms.mjs wcs config update --confirm-config --warehouse-id WH-ID --base-url https://wms-agv-sandbox.onrender.com --callback-url CALLBACK-URL
WMS_TOKEN=... node tools/wms.mjs wcs dispatch --dry-run --task-id TASK-ID
```

真实 live dispatch 仍需 operator 明确批准，并应只使用测试账号和 sandbox
任务。

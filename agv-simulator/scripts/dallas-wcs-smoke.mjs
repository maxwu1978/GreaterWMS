import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const port = Number.parseInt(process.env.AGV_SIM_PORT || process.env.PORT || "4291", 10);
const baseUrl = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ["server.mjs"], {
  cwd: new URL("..", import.meta.url),
  env: { ...process.env, AGV_SIM_PORT: String(port) },
  stdio: ["ignore", "pipe", "pipe"],
});

let serverOutput = "";
server.stdout.on("data", (chunk) => {
  serverOutput += chunk.toString();
});
server.stderr.on("data", (chunk) => {
  serverOutput += chunk.toString();
});

async function request(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: { "content-type": "application/json", ...(options.headers || {}) },
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(`${options.method || "GET"} ${path} failed with ${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

async function waitForHealth() {
  const started = Date.now();
  while (Date.now() - started < 5000) {
    try {
      const health = await request("/api/health");
      if (health.ok && health.service === "agv-simulator") return health;
    } catch {
      await delay(120);
    }
  }
  throw new Error(`AGV simulator did not become healthy. Output:\n${serverOutput}`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function pointInsideZone(point, zone) {
  const x = Number(point.x);
  const y = Number(point.y);
  return (
    x > Number(zone.x) + 0.01 &&
    x < Number(zone.x) + Number(zone.width) - 0.01 &&
    y > Number(zone.y) + 0.01 &&
    y < Number(zone.y) + Number(zone.height) - 0.01
  );
}

function assertRouteAvoidsZones(routePoints, zones, label) {
  for (let index = 1; index < routePoints.length; index += 1) {
    const from = routePoints[index - 1];
    const to = routePoints[index];
    for (let step = 0; step <= 40; step += 1) {
      const progress = step / 40;
      const sample = {
        x: Number(from.x) + (Number(to.x) - Number(from.x)) * progress,
        y: Number(from.y) + (Number(to.y) - Number(from.y)) * progress,
      };
      const crossedZone = zones.find((zone) => pointInsideZone(sample, zone));
      assert(!crossedZone, `${label} crosses floor-storage zone ${crossedZone?.code || ""}`);
    }
  }
}

try {
  const health = await waitForHealth();
  const layout = await request("/api/layouts/dallas");
  assert(layout.warehouse_code === "DAL", "Dallas layout warehouse code mismatch");
  assert(Array.isArray(layout.wcs_point_mapping_draft), "Dallas WCS point mapping draft is missing");
  assert(layout.layout_name === "Dallas AGV standard layout v2", "Dallas layout standard version mismatch");
  assert(layout.route_policy?.traffic_pattern === "controlled_one_way_loop", "Dallas route policy is missing");
  assert(layout.route_policy?.dock_doors_are_storage_locations === false, "Dock doors must not be storage locations");
  assert(Number(layout.route_policy?.abc_lower_lane_width_ft) >= 12, "ABC lower AGV lane width is missing");
  assert(Array.isArray(layout.agv_paths) && layout.agv_paths.length >= 5, "Dallas AGV paths are missing");
  assert(Array.isArray(layout.stations) && layout.stations.some((station) => station.station_role === "charging"), "Charging station is missing");
  assert(Array.isArray(layout.safety_zones) && layout.safety_zones.length >= 2, "Safety zones are missing");
  assert(layout.summary?.storage_points === 108, "Dallas storage point count should stay at 108 with lower lane outside storage");
  assert(layout.summary?.dock_points === 8, "Dallas dock point count should stay at 8");
  assert(layout.summary?.external_station_points === 3, "Dallas external station point count should stay at 3");

  const zoneA = layout.zones.find((zone) => zone.code === "DAL-A");
  const zoneB = layout.zones.find((zone) => zone.code === "DAL-B");
  const zoneC = layout.zones.find((zone) => zone.code === "DAL-C");
  const rackZone = layout.zones.find((zone) => zone.code === "DAL-RACK");
  const aConnector = layout.zones.find((zone) => zone.code === "A-CONN");
  const driveAisle = layout.zones.find((zone) => zone.code === "DRV");
  const lowerLane = layout.zones.find((zone) => zone.code === "ABC-LOWER");
  const dockZone = layout.zones.find((zone) => zone.code === "DOCK");
  assert(zoneA?.zone_type === "floor_storage", "A must be floor storage");
  assert(zoneB?.zone_type === "floor_storage", "B must be floor storage");
  assert(zoneC?.zone_type === "floor_storage", "C must be floor storage");
  assert(zoneA?.columns === 4 && zoneA?.rows === 4 && zoneA?.dimensions?.slot_count === 16, "A must show 16 oversized cargo slots");
  assert(zoneA?.dimensions?.capacity_adjustment?.lost_to_agv_connector_width_ft === 12, "A connector capacity adjustment is missing");
  assert(zoneA?.dimensions?.slot_layout?.slot_width_ft === 6, "A slot width should fit 68 in cargo side");
  assert(zoneA?.dimensions?.slot_layout?.slot_depth_ft === 5, "A slot depth should fit 58 in cargo side");
  assert(zoneA?.dimensions?.zone_depth_ft === 22, "A storage depth should keep 22 ft because lower lane is outside storage");
  assert(zoneB?.columns === 4 && zoneB?.rows === 4 && zoneB?.dimensions?.slot_count === 16, "B must show 16 oversized cargo slots");
  assert(zoneC?.columns === 4 && zoneC?.rows === 4 && zoneC?.dimensions?.slot_count === 16, "C must show 16 oversized cargo slots");
  assert(zoneB?.dimensions?.slot_layout?.slot_width_ft === 9, "B slot width should fit 104 in cargo side");
  assert(zoneC?.dimensions?.slot_layout?.slot_width_ft === 9, "C slot width should fit 104 in cargo side");
  assert(zoneB?.dimensions?.slot_layout?.residual_width_ft === 4, "B clear side band should be visible in slot layout");
  assert(zoneC?.dimensions?.slot_layout?.residual_width_ft === 4, "C clear side band should be visible in slot layout");
  assert(rackZone?.zone_type === "rack_storage" && rackZone.levels === 4, "Top rack row must be 4-level rack storage");
  assert(aConnector?.zone_type === "drive_aisle" && aConnector.create_locations === false, "A connector must be a non-storage AGV drive aisle");
  assert(lowerLane?.zone_type === "drive_aisle" && lowerLane.create_locations === false, "ABC lower lane must be an AGV drive aisle");
  assert(Number(aConnector.x) + Number(aConnector.width) <= Number(zoneA.x), "A connector must occupy the left side before A storage");
  assert(Number(zoneA.y) + Number(zoneA.height) <= Number(lowerLane.y), "ABC lower lane should sit below the floor-storage zones");
  assert(dockZone?.zone_type === "dock" && dockZone.create_locations === false, "Dock doors must be external dock points");
  assert(Number(zoneC.x) + Number(zoneC.width) <= Number(driveAisle.x), "C zone overlaps the drive aisle");
  const floorStorageZones = [zoneA, zoneB, zoneC];
  const routeNodeById = new Map(layout.route_nodes.map((node) => [node.id, node]));
  for (const path of layout.agv_paths) {
    assertRouteAvoidsZones(
      path.points.map((nodeId) => routeNodeById.get(nodeId)).filter(Boolean),
      floorStorageZones,
      path.id,
    );
  }

  const dockPoint =
    layout.wcs_point_mapping_draft.find((point) => point.point_code === "DAL-DOCK-DOCK-27") ||
    layout.wcs_point_mapping_draft.find((point) => point.point_type === "dock" || point.point_role === "dock");
  const storagePoint = layout.wcs_point_mapping_draft.find(
    (point) => point.location_barcode === "DAL-A-01-01-01-01",
  );
  assert(dockPoint?.point_code, "Dallas dock point is missing");
  assert(storagePoint?.point_code, "Dallas storage point is missing");
  assert(dockPoint.wcs_metadata?.external_point === true, "Dock point should be external WCS metadata");
  assert(storagePoint.wcs_metadata?.route_anchor_id === "N-A-FACE", "Storage point route anchor is missing");

  const psn = `DAL-SMOKE-${Date.now()}`;
  const created = await request("/api/wcs/transport-task", {
    method: "POST",
    body: JSON.stringify({
      wtaskinfoType: "AGV搬运",
      startPos: dockPoint.point_code,
      endPos: storagePoint.point_code,
      wtaskinfoPsn: psn,
      wtaskinfoReturnurl: `${baseUrl}/api/wcs/step-status`,
      wtaskinfoScode: layout.warehouse_code,
      wtaskinfoPalletSpec: "GMA",
      wtaskinfoOutparam: {
        layout_name: layout.layout_name,
        mapping_source: layout.source,
      },
    }),
  });
  assert(created.success === "true", "Transport task was not accepted");

  const taskId = created.data.wtaskinfoTid;
  let state = await request("/api/state");
  let task = state.tasks.find((item) => item.id === taskId);
  assert(task, "Created task not found in simulator state");
  assert(task.route.length >= 4, "Task route was not generated");
  assert(task.route[0].label === dockPoint.point_code, "Route does not start at mapped dock point");
  assert(task.route.at(-1).label === storagePoint.point_code, "Route does not end at mapped storage point");
  assert(task.route.some((point) => point.label === "Dock wait point"), "Route should include dock wait point");
  assert(task.route.some((point) => point.label === "Top wait point"), "Route should include top wait point");
  assert(task.route.some((point) => point.label === "A north edge handoff"), "Route should include A edge handoff");
  assertRouteAvoidsZones(task.route, floorStorageZones, "dock-to-storage task route");

  await request(`/api/tasks/${taskId}/start`, { method: "POST", body: "{}" });
  await request(`/api/tasks/${taskId}/pause`, { method: "POST", body: "{}" });
  await request(`/api/tasks/${taskId}/resume`, { method: "POST", body: "{}" });
  await request(`/api/tasks/${taskId}/reset`, { method: "POST", body: "{}" });
  await request(`/api/tasks/${taskId}/start`, { method: "POST", body: "{}" });
  await request(`/api/tasks/${taskId}/complete`, { method: "POST", body: "{}" });

  state = await request("/api/state");
  task = state.tasks.find((item) => item.id === taskId);
  assert(task.status === "completed", "Task did not reach completed state");
  assert(task.stepStatus === 30, "Completed task did not use WCS stepStatus=30");
  assert(state.exchanges.some((exchange) => exchange.taskId === taskId), "Exchange was not saved for task");

  const callbackState = await request("/api/wcs/callbacks");
  const callbacks = callbackState.callbacks.filter((callback) => callback.taskPsn === psn);
  const statuses = callbacks.map((callback) => callback.stepStatus).sort((left, right) => left - right);
  assert(statuses.includes(20), "Missing WCS running callback stepStatus=20");
  assert(statuses.includes(25), "Missing WCS paused callback stepStatus=25");
  assert(statuses.includes(30), "Missing WCS completed callback stepStatus=30");
  assert(callbacks.every((callback) => callback.stepStartpos === dockPoint.point_code), "Callback start point mismatch");
  assert(callbacks.every((callback) => callback.stepEndpos === storagePoint.point_code), "Callback end point mismatch");

  const exchanges = await request("/api/exchanges");
  const exchange = exchanges.exchanges.find((item) => item.taskId === taskId);
  assert(exchange?.callbacks?.length >= 3, "Saved exchange does not include WCS callbacks");
  const replay = await request(`/api/exchanges/${exchange.id}/replay`, {
    method: "POST",
    body: JSON.stringify({ latest_only: true }),
  });
  assert(replay.ok === true, "Exchange replay was not accepted");
  assert(replay.replays.length === 1, "Exchange replay should replay one callback by default");
  assert(replay.replays[0].responseStatus === 200, "Exchange replay did not reach local callback endpoint");

  const reverse = await request("/api/wcs/transport-task", {
    method: "POST",
    body: JSON.stringify({
      wtaskinfoType: "AGV搬运",
      startPos: storagePoint.point_code,
      endPos: dockPoint.point_code,
      wtaskinfoPsn: `DAL-SMOKE-RETURN-${Date.now()}`,
      wtaskinfoReturnurl: `${baseUrl}/api/wcs/step-status`,
      wtaskinfoScode: layout.warehouse_code,
      wtaskinfoPalletSpec: "GMA",
    }),
  });
  state = await request("/api/state");
  const reverseTask = state.tasks.find((item) => item.id === reverse.data.wtaskinfoTid);
  assert(reverseTask.route[0].label === storagePoint.point_code, "Return route should start at storage point");
  assert(reverseTask.route.at(-1).label === dockPoint.point_code, "Return route should end at dock point");
  assert(reverseTask.route.some((point) => point.label === "ABC lower AGV lane"), "Return route should include ABC lower AGV lane");
  assert(reverseTask.route.some((point) => point.label === "Return to dock corridor"), "Return route should use the return lane");
  assertRouteAvoidsZones(reverseTask.route, floorStorageZones, "storage-to-dock task route");

  const login = await request("/loginToken", {
    method: "POST",
    body: JSON.stringify({ username: "wcs-smoke", password: "sandbox" }),
  });
  assert(login.token, "WCS-compatible loginToken endpoint did not return a token");

  const vendorPsn = `DAL-SMOKE-WCS-${Date.now()}`;
  const vendorCreated = await request("/task/wlTaskInfo/addTransportTask", {
    method: "POST",
    headers: { token: login.token },
    body: JSON.stringify({
      wtaskinfoType: "AGV搬运",
      startPos: dockPoint.point_code,
      endPos: storagePoint.point_code,
      wtaskinfoPsn: vendorPsn,
      wtaskinfoReturnurl: `${baseUrl}/api/wcs/step-status`,
      wtaskinfoScode: layout.warehouse_code,
      wtaskinfoPalletSpec: "GMA",
    }),
  });
  assert(vendorCreated.success === "true", "WCS vendor transport endpoint was not accepted");
  assert(vendorCreated.data?.wtaskinfoTid, "WCS vendor transport endpoint did not return task id");

  const ready = await request("/task/wlReadyAgvRobot/editReadyConfig", {
    method: "POST",
    headers: { token: login.token },
    body: JSON.stringify({ wrarSign: dockPoint.point_code, wrarApiSign: "1", wrarApiNum: "1" }),
  });
  assert(ready.success === "true", "WCS ready-config endpoint was not accepted");

  const quality = await request("/QualityComplete", {
    method: "POST",
    headers: { token: login.token },
    body: JSON.stringify({ wtaskinfoPsn: vendorPsn, qualityStatus: "qualified" }),
  });
  assert(quality.success === "true", "WCS quality-complete endpoint was not accepted");

  const failedPsn = `DAL-SMOKE-FAIL-${Date.now()}`;
  const failed = await request("/api/wcs/transport-task", {
    method: "POST",
    body: JSON.stringify({
      wtaskinfoType: "AGV搬运",
      startPos: dockPoint.point_code,
      endPos: storagePoint.point_code,
      wtaskinfoPsn: failedPsn,
      wtaskinfoReturnurl: `${baseUrl}/api/wcs/step-status`,
      wtaskinfoScode: layout.warehouse_code,
    }),
  });
  const failedTaskId = failed.data.wtaskinfoTid;
  await request(`/api/tasks/${failedTaskId}/start`, { method: "POST", body: "{}" });
  await request(`/api/tasks/${failedTaskId}/fail`, { method: "POST", body: "{}" });
  state = await request("/api/state");
  const failedTask = state.tasks.find((item) => item.id === failedTaskId);
  assert(failedTask.status === "error", "Failed task did not reach error state");
  assert(failedTask.stepStatus === 40, "Failed task did not emit WCS stepStatus=40");

  console.log(
    JSON.stringify(
      {
        ok: true,
        health,
        layout: layout.layout_name,
        mapping_count: layout.wcs_point_mapping_draft.length,
        storage_points: layout.summary.storage_points,
        dock_points: layout.summary.dock_points,
        station_points: layout.summary.external_station_points,
        task_id: taskId,
        psn,
        route_points: task.route.map((point) => point.label),
        return_route_points: reverseTask.route.map((point) => point.label),
        callback_statuses: statuses,
        exchange_id: exchange.id,
        replay_status: replay.replays[0].responseStatus,
        vendor_task_id: vendorCreated.data.wtaskinfoTid,
        ready_exchange_id: ready.data.exchange_id,
        quality_exchange_id: quality.data.exchange_id,
        failed_task_id: failedTaskId,
      },
      null,
      2,
    ),
  );
} finally {
  server.kill("SIGTERM");
}

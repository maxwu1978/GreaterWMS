import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = fileURLToPath(new URL(".", import.meta.url));
const publicDir = join(rootDir, "public");
const dallasLayoutPath = join(rootDir, "fixtures", "dallas-layout-wcs-point-mapping-draft.json");
const port = Number.parseInt(process.env.AGV_SIM_PORT || process.env.PORT || "4179", 10);

const tasks = new Map();
const logs = [];
const callbacks = [];
const exchanges = [];
let taskSequence = 0;
const dallasLayoutSource = JSON.parse(await readFile(dallasLayoutPath, "utf8"));
const dallasLayout = buildDallasLayout(dallasLayoutSource);

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

function pushLog(event, detail = {}) {
  const record = { at: new Date().toISOString(), event, detail };
  logs.unshift(record);
  logs.splice(160);
  return record;
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body, null, 2);
  res.writeHead(status, {
    "access-control-allow-headers": "content-type,token",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-origin": "*",
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
  });
  res.end(payload);
}

async function readRequestJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (chunks.length === 0) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function normalizeStaticPath(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const requested = decoded === "/" ? "/index.html" : decoded;
  const safePath = normalize(requested).replace(/^(\.\.[/\\])+/, "");
  return join(publicDir, safePath);
}

async function serveStatic(req, res) {
  try {
    const filePath = normalizeStaticPath(req.url || "/");
    if (!filePath.startsWith(publicDir)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }
    const content = await readFile(filePath);
    res.writeHead(200, {
      "cache-control": "no-store",
      "content-type": mimeTypes[extname(filePath)] || "application/octet-stream",
    });
    res.end(content);
  } catch (error) {
    res.writeHead(error.code === "ENOENT" ? 404 : 500, {
      "content-type": "text/plain; charset=utf-8",
    });
    res.end(error.code === "ENOENT" ? "Not found" : "Server error");
  }
}

function numberFrom(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function pointFromNode(node, fallbackLabel) {
  if (!node) return null;
  return {
    x: numberFrom(node.x),
    y: numberFrom(node.y),
    label: node.label || node.id || fallbackLabel,
    node_id: node.id,
    role: node.role || null,
  };
}

function dallasNodeById(nodeId) {
  return dallasLayout.route_nodes.find((node) => node.id === nodeId);
}

function dallasPointByCode(pointCode) {
  return dallasLayout.wcs_point_mapping_draft.find((point) => point.point_code === pointCode);
}

function handoffPointFor(point, nodeId, fallbackLabel) {
  const nodePoint = pointFromNode(dallasNodeById(nodeId), fallbackLabel);
  if (!nodePoint) return simulatorPoint(point, fallbackLabel);
  return {
    ...nodePoint,
    label: point?.point_code || point?.location_barcode || fallbackLabel,
    point_role: point?.point_role || point?.point_type || null,
    route_anchor_id: point?.wcs_metadata?.route_anchor_id || null,
    route_exit_id: point?.wcs_metadata?.route_exit_id || point?.wcs_metadata?.route_anchor_id || null,
    zone_code: point?.wcs_metadata?.zone_code || null,
  };
}

function simulatorPoint(point, fallbackLabel) {
  if (!point?.coordinates) return null;
  return {
    x: point.coordinates.x,
    y: point.coordinates.y,
    label: point.point_code || point.location_barcode || fallbackLabel,
    point_role: point.point_role || point.point_type || null,
    route_anchor_id: point.wcs_metadata?.route_anchor_id || null,
    route_exit_id: point.wcs_metadata?.route_exit_id || point.wcs_metadata?.route_anchor_id || null,
    zone_code: point.wcs_metadata?.zone_code || null,
  };
}

function routeNodePoints(nodeIds) {
  return nodeIds
    .map((nodeId) => pointFromNode(dallasNodeById(nodeId), nodeId))
    .filter(Boolean);
}

function withoutDuplicateAdjacent(points) {
  return points.filter((point, index) => {
    if (!point) return false;
    const previous = points[index - 1];
    return !previous || previous.x !== point.x || previous.y !== point.y || previous.label !== point.label;
  });
}

function generatedLocationPoint(layout, zone, row, column, level, position) {
  const rowCode = String(row).padStart(2, "0");
  const columnCode = String(column).padStart(2, "0");
  const levelCode = String(level).padStart(2, "0");
  const positionCode = String(position).padStart(2, "0");
  const barcode = `${zone.code}-${rowCode}-${columnCode}-${levelCode}-${positionCode}`;
  const zoneWidth = numberFrom(zone.width, 10);
  const zoneHeight = numberFrom(zone.height, 10);
  const zoneX = numberFrom(zone.x, 0);
  const zoneY = numberFrom(zone.y, 0);
  const columns = Math.max(1, numberFrom(zone.columns, 1));
  const rows = Math.max(1, numberFrom(zone.rows, 1));
  const slotLayout = zone.dimensions?.slot_layout || {};
  const zoneWidthFt = numberFrom(slotLayout.zone_width_ft || zone.dimensions?.zone_width_ft, 0);
  const zoneDepthFt = numberFrom(slotLayout.zone_depth_ft || zone.dimensions?.zone_depth_ft, 0);
  const slotWidthFt = numberFrom(slotLayout.slot_width_ft || zone.dimensions?.pallet_width_ft, 0);
  const slotDepthFt = numberFrom(slotLayout.slot_depth_ft || zone.dimensions?.pallet_depth_ft, 0);
  const usesPhysicalSlotLayout = zoneWidthFt > 0 && zoneDepthFt > 0 && slotWidthFt > 0 && slotDepthFt > 0;
  const slotWidthPercent = usesPhysicalSlotLayout ? zoneWidth * (slotWidthFt / zoneWidthFt) : zoneWidth / columns;
  const slotHeightPercent = usesPhysicalSlotLayout ? zoneHeight * (slotDepthFt / zoneDepthFt) : zoneHeight / rows;
  const offsetXPercent = usesPhysicalSlotLayout ? zoneWidth * (numberFrom(slotLayout.offset_x_ft, 0) / zoneWidthFt) : 0;
  const offsetYPercent = usesPhysicalSlotLayout ? zoneHeight * (numberFrom(slotLayout.offset_y_ft, 0) / zoneDepthFt) : 0;
  const x = zoneX + offsetXPercent + (column - 0.5) * slotWidthPercent;
  const y = zoneY + offsetYPercent + (row - 0.5) * slotHeightPercent;
  const routeMetadata = zone.layout_metadata || {};

  return {
    location_barcode: barcode,
    point_code: `${layout.warehouse_code}-STO-${barcode}`,
    point_type: "storage",
    point_role: "storage",
    point_name:
      zone.zone_type === "rack_storage"
        ? `${zone.label || zone.code} rack ${columnCode} level ${levelCode}`
        : `${zone.label || zone.code} row ${rowCode} column ${columnCode}`,
    agv_reachable: true,
    coordinates: { x: Number(x.toFixed(3)), y: Number(y.toFixed(3)) },
    wcs_metadata: {
      source: "dallas_agv_standard_fixture",
      zone_code: zone.code,
      zone_type: zone.zone_type,
      pallet: zone.dimensions?.pallet || layout.planning_standard?.pallet_standard || null,
      route_anchor_id: routeMetadata.route_anchor_id,
      route_exit_id: routeMetadata.route_exit_id || routeMetadata.route_anchor_id,
      docking_direction: routeMetadata.docking_direction || null,
      route_role: routeMetadata.route_role || null,
      lane_policy: routeMetadata.lane_policy || null,
      layout_percent: {
        x: Number(x.toFixed(3)),
        y: Number(y.toFixed(3)),
        width: Number(slotWidthPercent.toFixed(3)),
        height: Number(slotHeightPercent.toFixed(3)),
      },
      dimensions: zone.dimensions || {},
    },
  };
}

function generatedDockPoint(layout, zone, doorNumber) {
  const anchorId = `N-DOCK-${doorNumber}`;
  const anchor = (layout.route_nodes || []).find((node) => node.id === anchorId);
  const doorX = numberFrom(zone.x, 90) + numberFrom(zone.width, 6) / 2;
  const y = numberFrom(anchor?.y, numberFrom(zone.y, 35));
  const code = `DOCK-${doorNumber}`;
  return {
    location_barcode: code,
    point_code: `${layout.warehouse_code}-DOCK-${code}`,
    point_type: "dock",
    point_role: "dock",
    point_name: `Dallas dock door ${doorNumber}`,
    station_role: "inbound_outbound",
    agv_reachable: true,
    virtual: true,
    coordinates: { x: Number(doorX.toFixed(3)), y },
    wcs_metadata: {
      source: "dallas_agv_standard_fixture",
      virtual: true,
      external_point: true,
      zone_code: zone.code,
      route_anchor_id: anchorId,
      docking_direction: zone.layout_metadata?.docking_direction || "west",
      route_role: "dock_door",
      dock_doors_are_storage_locations: false,
    },
  };
}

function generatedStationPoint(layout, station) {
  const role = station.station_role === "charging" ? "agv_station" : "buffer";
  return {
    location_barcode: station.code,
    point_code: `${layout.warehouse_code}-${role === "agv_station" ? "AGV" : "BUF"}-${station.code}`,
    point_type: role,
    point_role: role,
    point_name: station.name,
    station_role: station.station_role,
    agv_reachable: true,
    virtual: true,
    coordinates: { x: station.x, y: station.y },
    wcs_metadata: {
      source: "dallas_agv_standard_fixture",
      virtual: true,
      external_point: true,
      route_anchor_id: station.route_anchor_id,
      docking_direction: station.docking_direction || null,
      route_role: station.station_role,
    },
  };
}

function buildDallasPointMappings(layout) {
  const mappings = [];
  for (const zone of layout.zones || []) {
    if (!zone.create_locations) continue;
    const rows =
      zone.zone_type === "rack_storage"
        ? Math.max(1, numberFrom(zone.aisles, 1))
        : Math.max(1, numberFrom(zone.rows, 1));
    const columns = Math.max(1, numberFrom(zone.columns, 1));
    const levels = zone.zone_type === "rack_storage" ? Math.max(1, numberFrom(zone.levels || zone.rows, 4)) : 1;
    const positions = Math.max(1, numberFrom(zone.positions, 1));
    for (let row = 1; row <= rows; row += 1) {
      for (let column = 1; column <= columns; column += 1) {
        for (let level = 1; level <= levels; level += 1) {
          for (let position = 1; position <= positions; position += 1) {
            mappings.push(generatedLocationPoint(layout, zone, row, column, level, position));
          }
        }
      }
    }
  }
  const dockZone = (layout.zones || []).find((zone) => zone.zone_type === "dock");
  if (dockZone) {
    for (const doorNumber of dockZone.doors || []) {
      mappings.push(generatedDockPoint(layout, dockZone, doorNumber));
    }
  }
  for (const station of layout.stations || []) {
    mappings.push(generatedStationPoint(layout, station));
  }
  return mappings;
}

function buildDallasLayout(source) {
  const layout = JSON.parse(JSON.stringify(source));
  layout.wcs_point_mapping_draft = buildDallasPointMappings(layout);
  layout.summary = {
    storage_points: layout.wcs_point_mapping_draft.filter((point) => point.point_role === "storage").length,
    dock_points: layout.wcs_point_mapping_draft.filter((point) => point.point_role === "dock").length,
    external_station_points: layout.wcs_point_mapping_draft.filter(
      (point) => point.virtual && point.point_role !== "dock",
    ).length,
    agv_paths: (layout.agv_paths || []).length,
    route_nodes: (layout.route_nodes || []).length,
  };
  return layout;
}

function storageRouteZone(point) {
  return point?.zone_code || String(point?.label || "").split("-").slice(0, 2).join("-");
}

function topAisleToZone(zoneCode) {
  if (zoneCode === "DAL-C") return ["N-DOCK-NORTH", "N-WAIT-TOP", "N-TOP-C", "N-C-FACE"];
  if (zoneCode === "DAL-B") return ["N-DOCK-NORTH", "N-WAIT-TOP", "N-TOP-C", "N-TOP-B", "N-B-FACE"];
  if (zoneCode === "DAL-A") return ["N-DOCK-NORTH", "N-WAIT-TOP", "N-TOP-C", "N-TOP-B", "N-TOP-A", "N-A-FACE"];
  if (zoneCode === "DAL-RACK") {
    return ["N-DOCK-NORTH", "N-WAIT-TOP", "N-TOP-C", "N-TOP-B", "N-TOP-A", "N-RACK-FACE"];
  }
  return ["N-DOCK-NORTH", "N-WAIT-TOP"];
}

function returnLaneFromZone(zoneCode) {
  if (zoneCode === "DAL-A") return ["N-A-EXIT", "N-B-EXIT", "N-ABC-LOWER-LANE", "N-C-EXIT", "N-RETURN-CORRIDOR", "N-RETURN-DOCK"];
  if (zoneCode === "DAL-B") return ["N-B-EXIT", "N-ABC-LOWER-LANE", "N-C-EXIT", "N-RETURN-CORRIDOR", "N-RETURN-DOCK"];
  if (zoneCode === "DAL-C") return ["N-C-EXIT", "N-RETURN-CORRIDOR", "N-RETURN-DOCK"];
  if (zoneCode === "DAL-RACK") return ["N-RACK-FACE", "N-TOP-A", "N-TOP-B", "N-TOP-C", "N-WAIT-TOP", "N-DOCK-NORTH"];
  return ["N-RETURN-DOCK"];
}

function routeFor(startPos = "START", endPos = "END") {
  const startMapping = dallasPointByCode(startPos);
  const endMapping = dallasPointByCode(endPos);
  const dallasStart = simulatorPoint(startMapping, startPos);
  const dallasEnd = simulatorPoint(endMapping, endPos);
  if (dallasStart && dallasEnd) {
    const startIsDock = dallasStart.point_role === "dock";
    const endIsDock = dallasEnd.point_role === "dock";
    const startZone = storageRouteZone(dallasStart);
    const endZone = storageRouteZone(dallasEnd);
    const startAnchor = dallasStart.route_anchor_id;
    const endAnchor = dallasEnd.route_anchor_id;
    const startExit = dallasStart.route_exit_id || startAnchor;
    const routeStart = startIsDock ? dallasStart : handoffPointFor(startMapping, startExit, startPos);
    const routeEnd = endIsDock ? dallasEnd : handoffPointFor(endMapping, endAnchor, endPos);
    let nodeIds = [];
    if (startIsDock && !endIsDock) {
      nodeIds = [startAnchor, "N-WAIT-DOCK", ...topAisleToZone(endZone)];
    } else if (!startIsDock && endIsDock) {
      nodeIds = [...returnLaneFromZone(startZone), endAnchor];
    } else if (!startIsDock && !endIsDock) {
      nodeIds = [...returnLaneFromZone(startZone), "N-DOCK-NORTH", ...topAisleToZone(endZone)];
    } else {
      nodeIds = [startAnchor, "N-WAIT-DOCK", endAnchor];
    }
    return withoutDuplicateAdjacent([routeStart, ...routeNodePoints(nodeIds), routeEnd]);
  }
  const seed = [...`${startPos}:${endPos}`].reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const start = { x: 12 + (seed % 18), y: 70 - (seed % 12), label: startPos };
  const end = { x: 74 + (seed % 12), y: 22 + (seed % 18), label: endPos };
  return [
    start,
    { x: start.x + 12, y: start.y, label: "pickup" },
    { x: start.x + 12, y: 42, label: "aisle" },
    { x: end.x - 10, y: 42, label: "main aisle" },
    { x: end.x - 10, y: end.y, label: "drop lane" },
    end,
  ];
}

function createTaskFromTransport(payload) {
  taskSequence = (taskSequence + 1) % 1000;
  const id = String(Date.now() * 1000 + taskSequence);
  const task = {
    id,
    wtaskinfoTid: id,
    wtaskinfoPsn: payload.wtaskinfoPsn || `SIM-${id}`,
    wtaskinfoType: payload.wtaskinfoType || "AGV搬运",
    wtaskinfoOrder: payload.wtaskinfoOrder || "127",
    startPos: payload.startPos,
    endPos: payload.endPos,
    returnUrl: payload.wtaskinfoReturnurl,
    scode: payload.wtaskinfoScode || "SIM",
    palletSpec: payload.wtaskinfoPalletSpec || null,
    outparam: payload.wtaskinfoOutparam || {},
    status: "assigned",
    stepStatus: 10,
    stepStatusName: "待执行",
    progress: 0,
    agvUnitId: payload.agvip || "sim-agv-01",
    route: routeFor(payload.startPos, payload.endPos),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  tasks.set(id, task);
  const exchange = {
    id: `exchange-${id}`,
    taskId: id,
    taskPsn: task.wtaskinfoPsn,
    createdAt: task.createdAt,
    updatedAt: task.updatedAt,
    request: {
      method: "POST",
      endpoint: "/api/wcs/transport-task",
      body: payload,
    },
    callbacks: [],
    inbound_callbacks: [],
    replays: [],
  };
  task.exchangeId = exchange.id;
  exchanges.unshift(exchange);
  exchanges.splice(80);
  pushLog("task.created", { id, psn: task.wtaskinfoPsn, startPos: task.startPos, endPos: task.endPos });
  return task;
}

function exchangeForTask(task) {
  return exchanges.find((exchange) => exchange.taskId === task.id || exchange.taskPsn === task.wtaskinfoPsn);
}

function exchangeForPayload(payload) {
  const taskId = String(payload.taskTid || payload.wtaskinfoTid || "");
  const taskPsn = String(payload.taskPsn || payload.taskCode || payload.wtaskinfoPsn || "");
  return exchanges.find((exchange) => exchange.taskId === taskId || (taskPsn && exchange.taskPsn === taskPsn));
}

function isLocalReturnUrl(returnUrl) {
  try {
    const url = new URL(returnUrl);
    return ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
  } catch {
    return false;
  }
}

function recordExchangeCallback(task, delivery) {
  const exchange = exchangeForTask(task);
  if (!exchange) return;
  exchange.callbacks.unshift(delivery);
  exchange.callbacks.splice(40);
  exchange.updatedAt = new Date().toISOString();
}

function recordInboundCallback(payload, event) {
  const exchange = exchangeForPayload(payload);
  if (!exchange) return;
  exchange.inbound_callbacks.unshift(event);
  exchange.inbound_callbacks.splice(40);
  exchange.updatedAt = new Date().toISOString();
}

function recordSimpleExchange(endpoint, body) {
  const exchange = {
    id: `exchange-${Date.now()}-${exchanges.length + 1}`,
    taskId: null,
    taskPsn: body?.wtaskinfoPsn || body?.wrarSign || null,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    request: {
      method: "POST",
      endpoint,
      body,
    },
    callbacks: [],
    inbound_callbacks: [],
    replays: [],
  };
  exchanges.unshift(exchange);
  exchanges.splice(80);
  pushLog("exchange.recorded", { endpoint, exchangeId: exchange.id });
  return exchange;
}

function callbackPayload(task, stepStatus, stepStatusName, note = "") {
  const now = new Date().toISOString().slice(0, 19).replace("T", " ");
  return {
    stepTid: Number(task.wtaskinfoTid) + 1000,
    taskTid: Number(task.wtaskinfoTid),
    taskPsn: task.wtaskinfoPsn,
    taskScode: task.scode,
    taskType: task.wtaskinfoType,
    taskName: "AGV simulator transport task",
    taskOrder: Number(task.wtaskinfoOrder || 127),
    taskReturnurl: task.returnUrl,
    taskNodeNum: 1,
    stepOrder: 1,
    stepNode: "AGV搬运",
    stepStatus,
    stepStatusName,
    stepStartpos: task.startPos,
    stepEndpos: task.endPos,
    stepAgvIp: task.agvUnitId,
    stepNote: note || task.agvUnitId,
    taskAddtime: now,
    stepAddtime: now,
    stepStarttime: stepStatus >= 20 ? now : "",
    stepPickupTime: stepStatus >= 20 ? now : "",
    stepEndtime: stepStatus === 30 ? now : "",
    taskStarttime: stepStatus >= 20 ? now : "",
    taskEndtime: stepStatus === 30 ? now : "",
    wtaskinfoScanPsn: task.wtaskinfoPsn,
    taskPalletSpec: task.palletSpec,
  };
}

async function sendWcsCallback(task, stepStatus, stepStatusName, note) {
  const payload = callbackPayload(task, stepStatus, stepStatusName, note);
  const callbackEvent = { id: `local-${Date.now()}`, receivedAt: new Date().toISOString(), ...payload };
  const delivery = {
    id: `delivery-${Date.now()}`,
    sentAt: new Date().toISOString(),
    returnUrl: task.returnUrl || null,
    payload,
    skipped: false,
    responseStatus: null,
    responseBody: null,
    error: null,
  };
  callbacks.unshift(callbackEvent);
  callbacks.splice(100);
  if (!task.returnUrl) {
    delivery.skipped = true;
    recordExchangeCallback(task, delivery);
    pushLog("callback.skipped", { taskId: task.id, stepStatus, reason: "missing return URL" });
    return { skipped: true, payload };
  }
  try {
    const response = await fetch(task.returnUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await response.text();
    delivery.responseStatus = response.status;
    delivery.responseBody = text.slice(0, 500);
    recordExchangeCallback(task, delivery);
    pushLog("callback.sent", { taskId: task.id, stepStatus, status: response.status, response: text.slice(0, 240) });
    return { ok: response.ok, payload, response: text, status: response.status };
  } catch (error) {
    delivery.error = error.message;
    recordExchangeCallback(task, delivery);
    pushLog("callback.failed", { taskId: task.id, stepStatus, error: error.message });
    return { ok: false, payload, error: error.message };
  }
}

async function replayExchange(exchange, options = {}) {
  const callbacksToReplay = options.callback_id
    ? exchange.callbacks.filter((callback) => callback.id === options.callback_id)
    : exchange.callbacks.slice(0, options.latest_only === false ? exchange.callbacks.length : 1);
  const results = [];
  for (const callback of callbacksToReplay) {
    const returnUrl = options.return_url || callback.returnUrl || exchange.request?.body?.wtaskinfoReturnurl;
    const replay = {
      id: `replay-${Date.now()}-${results.length + 1}`,
      at: new Date().toISOString(),
      callbackId: callback.id,
      returnUrl: returnUrl || null,
      dryRun: Boolean(options.dry_run),
      skipped: false,
      responseStatus: null,
      responseBody: null,
      error: null,
    };
    if (!returnUrl) {
      replay.skipped = true;
      replay.error = "missing return URL";
      results.push(replay);
      continue;
    }
    if (!options.allow_external && !isLocalReturnUrl(returnUrl)) {
      replay.skipped = true;
      replay.error = "external return URL requires allow_external=true";
      results.push(replay);
      continue;
    }
    if (!options.dry_run) {
      try {
        const response = await fetch(returnUrl, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(callback.payload),
        });
        const text = await response.text();
        replay.responseStatus = response.status;
        replay.responseBody = text.slice(0, 500);
      } catch (error) {
        replay.error = error.message;
      }
    }
    results.push(replay);
  }
  exchange.replays.unshift(...results);
  exchange.replays.splice(40);
  exchange.updatedAt = new Date().toISOString();
  pushLog("exchange.replay", { exchangeId: exchange.id, count: results.length });
  return results;
}

async function setTaskState(task, action) {
  const transitions = {
    start: ["moving", 20, "执行中", Math.max(task.progress, 0.18), ""],
    pause: ["paused", 25, "暂停", task.progress, "simulated pause"],
    resume: ["moving", 20, "执行中", Math.max(task.progress, 0.35), ""],
    complete: ["completed", 30, "已完成", 1, ""],
    fail: ["error", 40, "异常", task.progress, "simulated AGV error"],
    reset: ["assigned", 10, "待执行", 0, ""],
  };
  const transition = transitions[action];
  if (!transition) throw new Error(`Unsupported simulator action: ${action}`);
  const [status, stepStatus, stepStatusName, progress, note] = transition;
  task.status = status;
  task.stepStatus = stepStatus;
  task.stepStatusName = stepStatusName;
  task.progress = progress;
  task.updatedAt = new Date().toISOString();
  pushLog("task.state", { taskId: task.id, status, stepStatus });
  if ([20, 25, 30, 40].includes(stepStatus)) await sendWcsCallback(task, stepStatus, stepStatusName, note);
  return task;
}

async function handleApi(req, res, url) {
  if (req.method === "OPTIONS") {
    sendJson(res, 200, { ok: true });
    return true;
  }
  if (req.method === "GET" && url.pathname === "/api/health") {
    sendJson(res, 200, { ok: true, service: "agv-simulator" });
    return true;
  }
  if (req.method === "GET" && url.pathname === "/api/state") {
    sendJson(res, 200, { tasks: [...tasks.values()], logs, exchanges });
    return true;
  }
  if (req.method === "GET" && url.pathname === "/api/layouts/dallas") {
    sendJson(res, 200, dallasLayout);
    return true;
  }
  if (req.method === "GET" && url.pathname === "/api/wcs/callbacks") {
    sendJson(res, 200, { callbacks });
    return true;
  }
  if (req.method === "GET" && url.pathname === "/api/exchanges") {
    sendJson(res, 200, { exchanges });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/api/wcs/transport-task") {
    const body = await readRequestJson(req);
    if (!body.startPos || !body.endPos) {
      sendJson(res, 400, { success: "false", msg: "startPos and endPos are required" });
      return true;
    }
    const task = createTaskFromTransport(body);
    sendJson(res, 200, {
      success: "true",
      msg: "created",
      data: { wtaskinfoTid: task.wtaskinfoTid, wtaskinfoPsn: task.wtaskinfoPsn },
    });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/task/wlTaskInfo/addTransportTask") {
    const body = await readRequestJson(req);
    if (!body.startPos || !body.endPos) {
      sendJson(res, 400, { success: "false", msg: "startPos and endPos are required" });
      return true;
    }
    const task = createTaskFromTransport(body);
    sendJson(res, 200, {
      success: "true",
      msg: "created",
      data: { wtaskinfoTid: task.wtaskinfoTid, wtaskinfoPsn: task.wtaskinfoPsn },
    });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/task/wlReadyAgvRobot/editReadyConfig") {
    const body = await readRequestJson(req);
    const exchange = recordSimpleExchange(url.pathname, body);
    sendJson(res, 200, { success: "true", msg: "ready config accepted", data: { exchange_id: exchange.id } });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/QualityComplete") {
    const body = await readRequestJson(req);
    const exchange = recordSimpleExchange(url.pathname, body);
    sendJson(res, 200, { success: "true", msg: "quality complete accepted", data: { exchange_id: exchange.id } });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/loginToken") {
    const body = await readRequestJson(req);
    const token = `sim-token-${Buffer.from(String(body.username || "wcs")).toString("hex").slice(0, 12)}`;
    sendJson(res, 200, { success: "true", msg: "login accepted", token, access_token: token, data: token });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/api/wcs/step-status") {
    const body = await readRequestJson(req);
    const event = { id: `cb-${Date.now()}-${callbacks.length + 1}`, receivedAt: new Date().toISOString(), ...body };
    callbacks.unshift(event);
    callbacks.splice(100);
    recordInboundCallback(body, event);
    pushLog("callback.accepted", { stepStatus: body.stepStatus, taskPsn: body.taskPsn || body.taskCode });
    sendJson(res, 200, { ok: true, message: "mock WCS stepStatus callback accepted", event });
    return true;
  }
  const replayMatch = url.pathname.match(/^\/api\/exchanges\/([^/]+)\/replay$/);
  if (req.method === "POST" && replayMatch) {
    const exchange = exchanges.find((item) => item.id === replayMatch[1]);
    if (!exchange) {
      sendJson(res, 404, { ok: false, error: "Exchange not found" });
      return true;
    }
    const body = await readRequestJson(req);
    const replays = await replayExchange(exchange, body);
    sendJson(res, 200, { ok: true, exchange_id: exchange.id, replays });
    return true;
  }
  if (req.method === "POST" && url.pathname === "/api/tasks/demo") {
    const task = createTaskFromTransport({
      wtaskinfoType: "AGV搬运",
      startPos: "DAL-DOCK-DOCK-27",
      endPos: "DAL-STO-DAL-A-01-01-01-01",
      wtaskinfoPsn: `DEMO-${Date.now()}`,
      wtaskinfoReturnurl: "",
      wtaskinfoScode: "DALLAS",
      wtaskinfoPalletSpec: "GMA",
    });
    sendJson(res, 200, { ok: true, task });
    return true;
  }
  const actionMatch = url.pathname.match(/^\/api\/tasks\/([^/]+)\/(start|pause|resume|complete|fail|reset)$/);
  if (req.method === "POST" && actionMatch) {
    const task = tasks.get(actionMatch[1]);
    if (!task) {
      sendJson(res, 404, { ok: false, error: "Task not found" });
      return true;
    }
    sendJson(res, 200, { ok: true, task: await setTaskState(task, actionMatch[2]) });
    return true;
  }
  return false;
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  try {
    if (await handleApi(req, res, url)) return;
    if (req.method === "GET") {
      await serveStatic(req, res);
      return;
    }
    sendJson(res, 405, { ok: false, error: "Method not allowed" });
  } catch (error) {
    pushLog("server.error", { error: error.message });
    sendJson(res, 500, { ok: false, error: error.message });
  }
});

server.listen(port, () => {
  console.log(`AGV simulator running at http://localhost:${port}`);
  console.log("WCS-style task endpoint: POST /api/wcs/transport-task");
});

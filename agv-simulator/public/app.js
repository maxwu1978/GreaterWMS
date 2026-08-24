const canvas = document.querySelector("#warehouseCanvas");
const ctx = canvas.getContext("2d");
const startBtn = document.querySelector("#startBtn");
const resetBtn = document.querySelector("#resetBtn");
const failBtn = document.querySelector("#failBtn");
const replayBtn = document.querySelector("#replayBtn");
const fullscreenBtn = document.querySelector("#fullscreenBtn");
const stepLabel = document.querySelector("#stepLabel");
const positionLabel = document.querySelector("#positionLabel");
const progressLabel = document.querySelector("#progressLabel");
const progressBar = document.querySelector("#progressBar");
const payloadView = document.querySelector("#payloadView");
const eventLog = document.querySelector("#eventLog");
const speedText = document.querySelector("#speedText");
const connectionText = document.querySelector("#connectionText");
const stepGrid = document.querySelector("#stepGrid");
const mapPane = document.querySelector(".map-pane");

const steps = [
  { status: 20, label: "到达取货点", progress: 0.34, routeIndex: 2 },
  { status: 30, label: "任务完成", progress: 1, routeIndex: 5 },
  { status: 40, label: "异常", progress: 1, routeIndex: 5, auto: false }
];

let map = {
  zones: [],
  routeNodes: [],
  agvPaths: [],
  stations: [],
  safetyZones: [],
  route: []
};

let dallasLayout = null;

let runState = {
  running: false,
  startedAt: 0,
  progress: 0,
  lastStepStatus: null,
  timer: null,
  animation: null,
  currentTaskId: null,
  taskCode: "TASK-PUTAWAY-0427",
  logs: []
};

function formatTime(date = new Date()) {
  return date.toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function addLog(message) {
  runState.logs.unshift({ time: formatTime(), message });
  runState.logs = runState.logs.slice(0, 60);
  eventLog.innerHTML = runState.logs
    .map((entry) => `<li><time>${entry.time}</time>${entry.message}</li>`)
    .join("");
}

function percentPointForCanvas(point) {
  return {
    x: Number(point.x || 0) * 12.8,
    y: Number(point.y || 0) * 7.6,
    label: point.label || point.id || point.code || "Point",
    role: point.role || point.station_role || point.zone_type || null
  };
}

function routePointForCanvas(point) {
  const x = Number(point.x);
  const y = Number(point.y);
  return {
    x: x <= 100 ? x * 12.8 : x,
    y: y <= 100 ? y * 7.6 : y,
    label: point.label || point.point_code || "Route point"
  };
}

function nodeById(nodeId) {
  return map.routeNodes.find((node) => node.id === nodeId);
}

function routeNodesForPath(path) {
  return (path.points || [])
    .map((nodeId) => nodeById(nodeId))
    .filter(Boolean)
    .map(percentPointForCanvas);
}

function defaultRouteFromLayout(layout) {
  const point = (nodeId) => nodeById(nodeId);
  return ["N-DOCK-27", "N-WAIT-DOCK", "N-DOCK-NORTH", "N-WAIT-TOP", "N-TOP-C", "N-C-FACE"]
    .map(point)
    .filter(Boolean)
    .map(percentPointForCanvas);
}

async function loadDallasLayout() {
  const response = await fetch("/api/layouts/dallas");
  const layout = await response.json();
  if (!response.ok) throw new Error(layout.error || "Could not load Dallas layout");
  dallasLayout = layout;
  map = {
    zones: layout.zones || [],
    routeNodes: layout.route_nodes || [],
    agvPaths: layout.agv_paths || [],
    stations: layout.stations || [],
    safetyZones: layout.safety_zones || [],
    route: []
  };
  addLog(`已加载 ${layout.layout_name}：${layout.summary?.storage_points || 0} 个库位点，${layout.agv_paths?.length || 0} 条路线`);
}

function loadRouteFromTask(task) {
  if (!Array.isArray(task?.route) || task.route.length < 2) return;
  map.route = task.route.map(routePointForCanvas);
  runState.currentTaskId = task.id;
  runState.taskCode = task.wtaskinfoPsn || task.id;
  document.querySelector("#taskCode").textContent = runState.taskCode;
}

async function ensureDemoTask() {
  if (runState.currentTaskId) return runState.currentTaskId;
  const response = await fetch("/api/tasks/demo", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}"
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || "Could not create demo task");
  loadRouteFromTask(payload.task);
  addLog(`已创建模拟任务 ${payload.task.wtaskinfoPsn}`);
  return payload.task.id;
}

async function applyTaskAction(action) {
  if (!runState.currentTaskId) return null;
  const response = await fetch(`/api/tasks/${encodeURIComponent(runState.currentTaskId)}/${action}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}"
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || `Task ${action} failed`);
  loadRouteFromTask(payload.task);
  return payload.task;
}

function interpolateRoute(progress) {
  const route = map.route;
  if (!route.length) return { x: 80, y: 80, label: "No route" };
  if (route.length === 1) return route[0];
  const scaled = progress * (route.length - 1);
  const index = Math.min(Math.floor(scaled), route.length - 2);
  const local = scaled - index;
  const from = route[index];
  const to = route[index + 1];
  return {
    x: from.x + (to.x - from.x) * local,
    y: from.y + (to.y - from.y) * local,
    label: local > 0.55 ? to.label : from.label
  };
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

function scaleForCanvas() {
  const rect = canvas.getBoundingClientRect();
  const scale = Math.min(rect.width / 1280, rect.height / 760);
  const offsetX = (rect.width - 1280 * scale) / 2;
  const offsetY = (rect.height - 760 * scale) / 2;
  return { scale, offsetX, offsetY };
}

function zoneRectForCanvas(zone) {
  return {
    x: Number(zone.x || 0) * 12.8,
    y: Number(zone.y || 0) * 7.6,
    w: Number(zone.width || zone.w || 1) * 12.8,
    h: Number(zone.height || zone.h || 1) * 7.6
  };
}

function storageSummary(zone) {
  const dims = zone.dimensions || {};
  const slotCount = Number(dims.slot_count || zone.rows * zone.columns || 0);
  const area = Number(dims.area_sqft || 0);
  const slotArea = Number(dims.slot_area_sqft || 0);
  if (!slotCount && !area) return zone.code;
  const parts = [];
  if (slotCount) parts.push(`${slotCount} slots`);
  if (slotArea) parts.push(`${slotArea.toFixed(1)} sqft/slot`);
  if (area) parts.push(`${area.toFixed(0)} sqft area`);
  return parts.join(" · ");
}

function slotCodeForZone(zone, row, column) {
  const prefix = String(zone.code || "Z").replace(/^DAL-/, "");
  return `${prefix}-${String(row + 1).padStart(2, "0")}-${String(column + 1).padStart(2, "0")}`;
}

function formatFt(value, fractionDigits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const digits = Number.isInteger(number) ? 0 : fractionDigits;
  return `${number.toFixed(digits)}ft`;
}

function formatDirection(direction) {
  return {
    northbound: "northbound",
    southbound: "southbound",
    eastbound: "eastbound",
    westbound: "westbound",
    eastbound_to_dock: "eastbound to dock",
    northbound_to_top_aisle: "northbound to top aisle",
    southbound_to_lower_lane: "southbound to lower lane"
  }[direction] || direction || "one-way";
}

function drawTextBadge(text, x, y, options = {}) {
  if (!text) return;
  const font = options.font || "700 12px Inter, sans-serif";
  ctx.save();
  ctx.font = font;
  const metrics = ctx.measureText(text);
  const padX = options.padX ?? 7;
  const padY = options.padY ?? 4;
  const height = options.height ?? 22;
  const width = Math.min(options.maxWidth || metrics.width + padX * 2, metrics.width + padX * 2);
  const boundedX = options.clamp === false ? x : Math.max(4, Math.min(x, 1276 - width));
  const boundedY = options.clamp === false ? y : Math.max(4, Math.min(y, 736 - height));
  ctx.fillStyle = options.background || "rgba(8, 13, 10, 0.82)";
  ctx.strokeStyle = options.border || "rgba(239, 244, 238, 0.28)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(boundedX, boundedY, width, height, 4);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = options.color || "#eff4ee";
  ctx.fillText(text, boundedX + padX, boundedY + height - padY - 3, Math.max(24, width - padX * 2));
  ctx.restore();
}

function drawCalloutBox(lines, x, y, width, options = {}) {
  const lineHeight = options.lineHeight || 15;
  const pad = options.pad || 8;
  const height = pad * 2 + lines.length * lineHeight;
  const boundedX = Math.max(4, Math.min(x, 1276 - width));
  const boundedY = Math.max(4, Math.min(y, 736 - height));
  ctx.save();
  ctx.fillStyle = options.background || "rgba(8, 13, 10, 0.88)";
  ctx.strokeStyle = options.border || "rgba(115, 193, 141, 0.9)";
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.roundRect(boundedX, boundedY, width, height, 5);
  ctx.fill();
  ctx.stroke();
  lines.forEach((line, index) => {
    ctx.fillStyle = index === 0 ? options.titleColor || "#eff4ee" : options.color || "#cfe5d5";
    ctx.font = index === 0 ? "800 12px Inter, sans-serif" : "700 10px Inter, sans-serif";
    ctx.fillText(line, boundedX + pad, boundedY + pad + 11 + index * lineHeight, width - pad * 2);
  });
  ctx.restore();
  return { x: boundedX, y: boundedY, w: width, h: height };
}

function drawReserveStrip(rect, label, horizontal = false) {
  ctx.save();
  ctx.fillStyle = "rgba(245, 184, 91, 0.08)";
  ctx.strokeStyle = "rgba(245, 184, 91, 0.62)";
  ctx.setLineDash([6, 5]);
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.roundRect(rect.x, rect.y, Math.max(1, rect.w), Math.max(1, rect.h), 3);
  ctx.fill();
  ctx.stroke();
  ctx.restore();

  if (rect.w > 30 && rect.h > 16) {
    ctx.save();
    ctx.fillStyle = "#f7d5a2";
    ctx.font = "700 10px Inter, sans-serif";
    if (horizontal) {
      ctx.fillText(label, rect.x + 6, rect.y + Math.min(16, rect.h - 3), Math.max(20, rect.w - 8));
    } else {
      ctx.translate(rect.x + rect.w / 2, rect.y + rect.h / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = "center";
      ctx.fillText(label, 0, 3, Math.max(20, rect.h - 8));
    }
    ctx.restore();
  }
}

function drawFloorStorageSlots(zone, rect) {
  const dims = zone.dimensions || {};
  const layout = dims.slot_layout || {};
  const rows = Math.max(1, Number(layout.rows || zone.rows || 1));
  const columns = Math.max(1, Number(layout.columns || zone.columns || 1));
  const slotWidthFt = Number(layout.slot_width_ft || dims.pallet_width_ft || 4);
  const slotDepthFt = Number(layout.slot_depth_ft || dims.pallet_depth_ft || 3.33);
  const zoneWidthFt = Math.max(0.1, Number(layout.zone_width_ft || dims.zone_width_ft || columns * slotWidthFt));
  const zoneDepthFt = Math.max(0.1, Number(layout.zone_depth_ft || dims.zone_depth_ft || rows * slotDepthFt));
  const offsetXFt = Number(layout.offset_x_ft || 0);
  const offsetYFt = Number(layout.offset_y_ft || 0);
  const pxPerFtX = rect.w / zoneWidthFt;
  const pxPerFtY = rect.h / zoneDepthFt;
  const slotW = Math.max(3, slotWidthFt * pxPerFtX);
  const slotH = Math.max(3, slotDepthFt * pxPerFtY);
  const originX = rect.x + offsetXFt * pxPerFtX;
  const originY = rect.y + offsetYFt * pxPerFtY;
  const occupiedW = columns * slotW;
  const occupiedH = rows * slotH;
  const residualWidthFt = Math.max(0, Number(layout.residual_width_ft || zoneWidthFt - offsetXFt - columns * slotWidthFt));
  const residualDepthFt = Math.max(0, Number(layout.residual_depth_ft || zoneDepthFt - offsetYFt - rows * slotDepthFt));

  if (residualWidthFt > 0.05) {
    drawReserveStrip(
      {
        x: originX + occupiedW,
        y: rect.y,
        w: residualWidthFt * pxPerFtX,
        h: rect.h
      },
      `${residualWidthFt.toFixed(1)}ft clear`
    );
  }
  if (residualDepthFt > 0.05) {
    drawReserveStrip(
      {
        x: rect.x,
        y: originY + occupiedH,
        w: rect.w,
        h: residualDepthFt * pxPerFtY
      },
      `${residualDepthFt.toFixed(1)}ft edge`,
      true
    );
  }

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < columns; col += 1) {
      const x = originX + col * slotW;
      const y = originY + row * slotH;
      ctx.fillStyle = "#173422";
      ctx.strokeStyle = "#73c18d";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(x + 2, y + 2, Math.max(4, slotW - 4), Math.max(4, slotH - 4), 3);
      ctx.fill();
      ctx.stroke();

      if (slotW > 42 && slotH > 18) {
        ctx.fillStyle = "#dff5e5";
        ctx.font = "700 10px Inter, sans-serif";
        ctx.fillText(slotCodeForZone(zone, row, col), x + 6, y + 15, Math.max(18, slotW - 10));
        if (row === 0 && col === 0 && slotH > 34) {
          ctx.fillStyle = "#b7d7bf";
          ctx.font = "700 9px Inter, sans-serif";
          ctx.fillText(`${slotWidthFt}x${slotDepthFt.toFixed(2)}ft`, x + 6, y + 29, Math.max(18, slotW - 10));
        }
      }
    }
  }
}

function drawRackSlots(zone, rect) {
  const rows = Math.max(1, Number(zone.rows || 1));
  const columns = Math.max(1, Number(zone.columns || 1));
  const padX = 24;
  const padY = 30;
  const slotW = Math.max(10, (rect.w - padX * 2) / columns - 4);
  const slotH = Math.max(8, (rect.h - padY - 14) / rows - 4);
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < columns; col += 1) {
      const x = rect.x + padX + col * (slotW + 4);
      const y = rect.y + padY + row * (slotH + 4);
      ctx.fillStyle = "#111a22";
      ctx.strokeStyle = "#5f7183";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(x, y, slotW, slotH, 3);
      ctx.fill();
      ctx.stroke();
    }
  }
}

function drawZone(zone) {
  const rect = zoneRectForCanvas(zone);
  const colors = {
    floor_storage: "#21392d",
    rack_storage: "#293443",
    drive_aisle: "#2b2736",
    dock: "#3c2722"
  };
  const zoneType = zone.zone_type || zone.type || "storage";
  ctx.fillStyle = colors[zoneType] || "#252f37";
  ctx.strokeStyle = zoneType === "drive_aisle" ? "#a988ff" : "#445047";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.roundRect(rect.x, rect.y, rect.w, rect.h, 6);
  if (zoneType === "drive_aisle") {
    ctx.save();
    ctx.globalAlpha = 0.45;
    ctx.fill();
    ctx.restore();
  } else {
    ctx.fill();
  }
  ctx.stroke();

  const labelX = rect.x + Math.min(18, Math.max(8, rect.w * 0.15));
  const labelMaxWidth = Math.max(24, rect.w - (labelX - rect.x) - 8);
  const zoneTitle =
    zoneType === "dock" ? "Dock doors" : zoneType === "drive_aisle" ? "AGV corridor" : zone.label || zone.code;
  if (zoneType !== "floor_storage") {
    ctx.fillStyle = "#dce7dd";
    ctx.font = `${rect.w < 96 ? "700 13px" : "700 18px"} Inter, sans-serif`;
    ctx.fillText(zoneTitle, labelX, rect.y + 30, labelMaxWidth);
    ctx.fillStyle = "#8f9c92";
    ctx.font = "12px Inter, sans-serif";
    ctx.fillText(zone.code, labelX, rect.y + 50, labelMaxWidth);
  }

  if (zoneType === "drive_aisle") {
    const widthFt = formatFt(zone.dimensions?.width_ft);
    const direction = formatDirection(zone.layout_metadata?.direction);
    ctx.fillStyle = "#d9cfff";
    ctx.font = "700 11px Inter, sans-serif";
    ctx.fillText([widthFt, direction].filter(Boolean).join(" · "), labelX, rect.y + 68, labelMaxWidth);
  }

  if (zoneType === "floor_storage") drawFloorStorageSlots(zone, rect);
  if (zoneType === "rack_storage") drawRackSlots(zone, rect);

  if (zoneType === "dock") {
    const doors = zone.doors || [];
    const doorH = rect.h / Math.max(doors.length, 1);
    doors.forEach((door, index) => {
      const y = rect.y + index * doorH;
      ctx.fillStyle = "#4a1f18";
      ctx.strokeStyle = "#ef6f6c";
      ctx.strokeRect(rect.x + 4, y + 3, rect.w - 8, Math.max(12, doorH - 6));
      ctx.fillStyle = "#ffb7aa";
      ctx.font = "700 11px Inter, sans-serif";
      ctx.fillText(String(door), rect.x + 14, y + Math.max(18, doorH / 2));
    });
  }
}

function drawSafetyZone(zone) {
  const rect = {
    x: Number(zone.x || 0) * 12.8,
    y: Number(zone.y || 0) * 7.6,
    w: Number(zone.width || 1) * 12.8,
    h: Number(zone.height || 1) * 7.6
  };
  ctx.save();
  ctx.setLineDash([10, 8]);
  ctx.strokeStyle = zone.zone_type === "safe_boundary" ? "#f5b85b" : "#ef6f6c";
  ctx.lineWidth = 2;
  ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
  ctx.restore();
}

function pathColor(path) {
  if (path.role === "return_lane") return "#d28d5e";
  if (path.role === "connector_aisle") return "#f5b85b";
  if (path.role === "charger") return "#f5b85b";
  return "#e45454";
}

function laneBandWidth(path) {
  const widthFt = Number(path.width_ft || 0);
  if (!Number.isFinite(widthFt) || widthFt <= 0) return 22;
  return Math.max(22, Math.min(44, widthFt));
}

function drawPathPolyline(points, strokeStyle, lineWidth, alpha = 1) {
  if (points.length < 2) return;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = strokeStyle;
  ctx.lineWidth = lineWidth;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.stroke();
  ctx.restore();
}

function drawArrowHead(x, y, angle, color, size = 9) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = color;
  ctx.strokeStyle = "rgba(8, 13, 10, 0.75)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(size, 0);
  ctx.lineTo(-size * 0.7, size * 0.62);
  ctx.lineTo(-size * 0.35, 0);
  ctx.lineTo(-size * 0.7, -size * 0.62);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawPathDirection(points, color) {
  for (let index = 1; index < points.length; index += 1) {
    const from = points[index - 1];
    const to = points[index];
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.hypot(dx, dy);
    if (length < 42) continue;
    const angle = Math.atan2(dy, dx);
    const arrowCount = length > 220 ? 2 : 1;
    for (let arrowIndex = 0; arrowIndex < arrowCount; arrowIndex += 1) {
      const ratio = arrowCount === 1 ? 0.58 : 0.35 + arrowIndex * 0.35;
      drawArrowHead(from.x + dx * ratio, from.y + dy * ratio, angle, color, 8);
    }
  }
}

function longestSegment(points) {
  let best = null;
  for (let index = 1; index < points.length; index += 1) {
    const from = points[index - 1];
    const to = points[index];
    const length = Math.hypot(to.x - from.x, to.y - from.y);
    if (!best || length > best.length) best = { from, to, length };
  }
  return best;
}

function drawPathLabel(path, points, color) {
  const segment = longestSegment(points);
  if (!segment || segment.length < 55) return;
  const width = formatFt(path.width_ft);
  const direction = formatDirection(path.direction);
  const label = `${path.label || path.id}${width ? ` · ${width}` : ""} · ${direction}`;
  const midX = (segment.from.x + segment.to.x) / 2;
  const midY = (segment.from.y + segment.to.y) / 2;
  const isVertical = Math.abs(segment.to.y - segment.from.y) > Math.abs(segment.to.x - segment.from.x);
  drawTextBadge(label, midX + (isVertical ? 10 : -120), midY + (isVertical ? -10 : -34), {
    background: "rgba(8, 13, 10, 0.88)",
    border: color,
    color: "#eff4ee",
    maxWidth: 320
  });
}

function drawAgvPaths() {
  map.agvPaths.forEach((path) => {
    const points = routeNodesForPath(path);
    if (points.length < 2) return;
    const color = pathColor(path);
    drawPathPolyline(points, color, laneBandWidth(path), 0.2);
  });

  map.agvPaths.forEach((path) => {
    const points = routeNodesForPath(path);
    if (points.length < 2) return;
    const color = pathColor(path);
    drawPathPolyline(points, color, path.role === "main_aisle" ? 6 : 4);
    drawPathDirection(points, color);
    drawPathLabel(path, points, color);
  });
}

function drawDimensionLine(x1, y1, x2, y2, label, vertical = false) {
  ctx.save();
  ctx.strokeStyle = "#f5d37f";
  ctx.fillStyle = "#f5d37f";
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  const tick = 5;
  if (vertical) {
    ctx.beginPath();
    ctx.moveTo(x1 - tick, y1);
    ctx.lineTo(x1 + tick, y1);
    ctx.moveTo(x2 - tick, y2);
    ctx.lineTo(x2 + tick, y2);
    ctx.stroke();
    ctx.translate(x1 - 12, (y1 + y2) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.font = "700 10px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(label, 0, 0);
  } else {
    ctx.beginPath();
    ctx.moveTo(x1, y1 - tick);
    ctx.lineTo(x1, y1 + tick);
    ctx.moveTo(x2, y2 - tick);
    ctx.lineTo(x2, y2 + tick);
    ctx.stroke();
    ctx.font = "700 10px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(label, (x1 + x2) / 2, y1 + 14);
  }
  ctx.restore();
}

function drawStorageAnnotations() {
  map.zones
    .filter((zone) => (zone.zone_type || zone.type) === "floor_storage")
    .forEach((zone, index) => {
      const rect = zoneRectForCanvas(zone);
      const dims = zone.dimensions || {};
      const layout = dims.slot_layout || {};
      const zoneWidthFt = Number(dims.zone_width_ft || layout.zone_width_ft || 0);
      const zoneDepthFt = Number(dims.zone_depth_ft || layout.zone_depth_ft || 0);
      const areaSqft = Number(dims.area_sqft || 0);
      const slotCount = Number(dims.slot_count || zone.rows * zone.columns || 0);
      const slotWidthFt = Number(layout.slot_width_ft || dims.pallet_width_ft || 4);
      const slotDepthFt = Number(layout.slot_depth_ft || dims.pallet_depth_ft || 3.33);
      const zoneCode = String(zone.code || "").replace(/^DAL-/, "");
      const cargo = dims.cargo_size_in;
      const calloutPositions = [
        { x: 96, y: 450 },
        { x: 370, y: 450 },
        { x: 645, y: 450 }
      ];
      const position = calloutPositions[index] || {
        x: rect.x + rect.w / 2 - 116,
        y: Math.min(650, rect.y + rect.h + 110)
      };
      const lines = [
        `${zoneCode}: ${formatFt(zoneWidthFt)} x ${formatFt(zoneDepthFt)} · ${areaSqft.toFixed(0)} sqft`,
        `${slotCount} slots · each ${formatFt(slotWidthFt)} x ${formatFt(slotDepthFt, 2)} x ${formatFt(dims.height_ft)}`,
        cargo ? `cargo ${cargo.length} x ${cargo.width} x ${cargo.height} in` : "cargo size pending"
      ];
      const callout = drawCalloutBox(lines, position.x, position.y, 236, {
        border: "rgba(115, 193, 141, 0.9)"
      });
      ctx.save();
      ctx.strokeStyle = "rgba(115, 193, 141, 0.78)";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(rect.x + rect.w / 2, rect.y + rect.h + 3);
      ctx.lineTo(callout.x + callout.w / 2, callout.y);
      ctx.stroke();
      ctx.restore();

      const adjustment = dims.capacity_adjustment || {};
      if (Number(adjustment.slot_delta || 0) < 0) {
        drawTextBadge(`after A-CONN: ${adjustment.slot_delta} slots`, callout.x + 8, callout.y + callout.h + 5, {
          background: "rgba(245, 184, 91, 0.18)",
          border: "rgba(245, 184, 91, 0.8)",
          color: "#ffe4aa",
          font: "700 10px Inter, sans-serif",
          height: 19,
          maxWidth: rect.w - 12
        });
      }
    });
}

function drawAllocationSummary() {
  const allocation = dallasLayout?.physical_allocation;
  if (!allocation) return;
  const widthParts = (allocation.abc_width_segments || [])
    .map((segment) => `${segment.label} ${segment.width_ft}ft`)
    .join(" + ");
  const depthParts = (allocation.abc_depth_segments || [])
    .map((segment) => `${segment.label} ${segment.depth_ft}ft`)
    .join(" + ");
  const lines = [
    `ABC width: ${allocation.abc_total_width_ft}ft = ${widthParts}`,
    `Rack-to-ABC depth: ${allocation.abc_to_rack_depth_ft}ft = ${depthParts}`
  ];
  if (allocation.abc_lower_lane_outside_storage_ft) {
    lines.push(`Lower AGV lane: ${allocation.abc_lower_lane_outside_storage_ft}ft outside ABC storage`);
  }
  drawCalloutBox(
    lines,
    112,
    590,
    680,
    {
      border: "rgba(245, 184, 91, 0.86)",
      background: "rgba(8, 13, 10, 0.9)",
      titleColor: "#ffe4aa",
      color: "#ffe4aa",
      lineHeight: 16
    }
  );
}

function drawStations() {
  map.stations.forEach((station) => {
    const point = percentPointForCanvas(station);
    ctx.fillStyle = station.station_role === "charging" ? "#f5b85b" : "#5ba8ff";
    ctx.strokeStyle = "#eff4ee";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(point.x, point.y, 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#eff4ee";
    ctx.font = "700 12px Inter, sans-serif";
    ctx.fillText(station.code, point.x + 14, point.y - 8);
  });
}

function drawRoute() {
  const route = map.route;
  if (route.length < 2) return;
  ctx.strokeStyle = "#5ba8ff";
  ctx.lineWidth = 8;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  route.forEach((point, index) => {
    if (index === 0) {
      ctx.moveTo(point.x, point.y);
    } else {
      ctx.lineTo(point.x, point.y);
    }
  });
  ctx.stroke();
  drawPathDirection(route, "#5ba8ff");

  route.forEach((point, index) => {
    ctx.fillStyle = index === 0 || index === route.length - 1 ? "#5ed28a" : "#101310";
    ctx.strokeStyle = "#b5c2b8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(point.x, point.y, 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  });
}

function drawAgv(position) {
  ctx.save();
  ctx.translate(position.x, position.y);
  ctx.fillStyle = "#eff4ee";
  ctx.strokeStyle = "#0a0d0b";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.roundRect(-18, -13, 36, 26, 5);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#5ed28a";
  ctx.beginPath();
  ctx.arc(0, 0, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  ctx.fillStyle = "#eff4ee";
  ctx.font = "700 13px Inter, sans-serif";
  ctx.fillText("AGV-01", position.x + 24, position.y - 16);
}

function draw() {
  const rect = canvas.getBoundingClientRect();
  const { scale, offsetX, offsetY } = scaleForCanvas();
  ctx.clearRect(0, 0, rect.width, rect.height);

  ctx.save();
  ctx.translate(offsetX, offsetY);
  ctx.scale(scale, scale);

  ctx.fillStyle = "#101310";
  ctx.fillRect(0, 0, 1280, 760);

  ctx.strokeStyle = "#202720";
  ctx.lineWidth = 1;
  for (let x = 40; x < 1280; x += 40) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, 760);
    ctx.stroke();
  }
  for (let y = 40; y < 760; y += 40) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(1280, y);
    ctx.stroke();
  }

  map.zones.forEach(drawZone);
  map.safetyZones.forEach(drawSafetyZone);
  drawAgvPaths();
  drawStorageAnnotations();
  drawAllocationSummary();
  drawRoute();
  drawStations();
  if (map.route.length >= 2) drawAgv(interpolateRoute(runState.progress));

  ctx.restore();
}

function renderSteps() {
  stepGrid.innerHTML = steps
    .map((step) => {
      const isDone = runState.lastStepStatus && step.status <= runState.lastStepStatus;
      const isActive = step.status === runState.lastStepStatus;
      const className = `step-pill${isDone ? " done" : ""}${isActive ? " active" : ""}`;
      return `<div class="${className}"><span>${step.status}</span><small>${step.label}</small></div>`;
    })
    .join("");
}

function updateStatus() {
  const position = map.route.length >= 2 ? interpolateRoute(runState.progress) : null;
  positionLabel.textContent = position ? `${position.label} (${Math.round(position.x)}, ${Math.round(position.y)})` : "-";
  progressLabel.textContent = `${Math.round(runState.progress * 100)}%`;
  progressBar.style.width = `${runState.progress * 100}%`;
  speedText.textContent = runState.running ? "1.2 m/s" : "0.0 m/s";

  const activeStep = steps.find((step) => step.status === runState.lastStepStatus);
  stepLabel.textContent = activeStep ? `${activeStep.status} ${activeStep.label}` : runState.running ? "执行中" : "待开始";
  renderSteps();
  draw();
}

function buildCallback(step) {
  const position = interpolateRoute(step.progress);
  return {
    reqCode: `SIM-${Date.now()}`,
    taskTid: Number(runState.currentTaskId) || runState.currentTaskId || "TASK-PUTAWAY-0427",
    taskCode: runState.taskCode,
    taskPsn: runState.taskCode,
    agvCode: "AGV-01",
    stepStatus: step.status,
    stepStatusName: step.label,
    stepStartpos: map.route[0]?.label || "START",
    stepEndpos: map.route.at(-1)?.label || "END",
    currentPosition: {
      locationCode: position.label,
      x: Number(position.x.toFixed(2)),
      y: Number(position.y.toFixed(2))
    },
    timestamp: new Date().toISOString()
  };
}

async function sendCallback(step) {
  const payload = buildCallback(step);
  payloadView.textContent = JSON.stringify(payload, null, 2);
  runState.lastStepStatus = step.status;
  addLog(`模拟 WCS 回调 stepStatus=${step.status} ${step.label}`);
  updateStatus();

  try {
    const response = await fetch("/api/wcs/step-status", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    connectionText.textContent = result.ok ? "Mock callback accepted" : "Mock callback rejected";
  } catch (error) {
    connectionText.textContent = "Callback endpoint unavailable";
    addLog(`本地回调接口不可用：${error.message}`);
  }
}

function tick() {
  if (!runState.running) {
    return;
  }

  const elapsed = Date.now() - runState.startedAt;
  runState.progress = Math.min(elapsed / 12000, 1);

  for (const step of steps) {
    if (step.auto !== false && runState.progress >= step.progress && (!runState.lastStepStatus || runState.lastStepStatus < step.status)) {
      sendCallback(step);
    }
  }

  updateStatus();

  if (runState.progress >= 1) {
    runState.running = false;
    startBtn.textContent = "Start";
    applyTaskAction("complete").catch((error) => addLog(`完成状态同步失败：${error.message}`));
    addLog("任务完成，AGV 已到达目标点");
    updateStatus();
    return;
  }

  runState.animation = requestAnimationFrame(tick);
}

async function startSimulation() {
  if (runState.running) {
    runState.running = false;
    startBtn.textContent = "Resume";
    applyTaskAction("pause").catch((error) => addLog(`暂停状态同步失败：${error.message}`));
    addLog("模拟暂停");
    updateStatus();
    return;
  }

  try {
    await ensureDemoTask();
    await applyTaskAction(runState.progress > 0 ? "resume" : "start");
    runState.running = true;
    runState.startedAt = Date.now() - runState.progress * 12000;
    startBtn.textContent = "Pause";
    addLog(`模拟开始：AGV-01 接收 ${runState.taskCode}`);
    tick();
  } catch (error) {
    connectionText.textContent = "Task start failed";
    addLog(`任务启动失败：${error.message}`);
  }
}

async function resetSimulation() {
  runState.running = false;
  runState.progress = 0;
  runState.lastStepStatus = null;
  payloadView.textContent = "{}";
  startBtn.textContent = "Start";
  await applyTaskAction("reset").catch((error) => addLog(`重置状态同步失败：${error.message}`));
  addLog("模拟已重置");
  updateStatus();
}

async function failSimulation() {
  try {
    await ensureDemoTask();
    runState.running = false;
    startBtn.textContent = "Resume";
    const failureStep = steps.find((step) => step.status === 40);
    await sendCallback({ ...failureStep, progress: Math.max(runState.progress, 0.5) });
    await applyTaskAction("fail");
    addLog("已模拟 AGV 异常，WCS stepStatus=40");
  } catch (error) {
    connectionText.textContent = "Fail action unavailable";
    addLog(`异常模拟失败：${error.message}`);
  } finally {
    updateStatus();
  }
}

async function replayLastExchange() {
  try {
    const response = await fetch("/api/exchanges");
    const payload = await response.json();
    const exchange =
      payload.exchanges?.find((item) => item.taskId === runState.currentTaskId) || payload.exchanges?.[0];
    if (!exchange) throw new Error("No saved exchange");
    const replayResponse = await fetch(`/api/exchanges/${encodeURIComponent(exchange.id)}/replay`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ latest_only: true })
    });
    const replayPayload = await replayResponse.json();
    if (!replayResponse.ok || !replayPayload.ok) throw new Error(replayPayload.error || "Replay failed");
    payloadView.textContent = JSON.stringify(replayPayload, null, 2);
    addLog(`已回放 exchange ${exchange.id}`);
  } catch (error) {
    connectionText.textContent = "Replay unavailable";
    addLog(`回放失败：${error.message}`);
  }
}

async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) {
      await mapPane.requestFullscreen();
    } else {
      await document.exitFullscreen();
    }
  } finally {
    setTimeout(resizeCanvas, 80);
  }
}

async function init() {
  try {
    await loadDallasLayout();
  } catch (error) {
    connectionText.textContent = "Layout unavailable";
    addLog(`Dallas 布局加载失败：${error.message}`);
  }

  steps.forEach((step) => {
    if (step.auto === false) {
      addLog(`已装载 stepStatus=${step.status}，通过 Fail 手动触发`);
      return;
    }
    const delay = Math.round(step.progress * 12);
    addLog(`已装载 stepStatus=${step.status}，预计 T+${delay}s 触发`);
  });

  startBtn.addEventListener("click", startSimulation);
  resetBtn.addEventListener("click", resetSimulation);
  failBtn.addEventListener("click", failSimulation);
  replayBtn.addEventListener("click", replayLastExchange);
  fullscreenBtn.addEventListener("click", toggleFullscreen);
  window.addEventListener("resize", resizeCanvas);
  document.addEventListener("fullscreenchange", resizeCanvas);
  resizeCanvas();
  updateStatus();
}

init();

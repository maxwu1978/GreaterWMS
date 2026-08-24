import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "../..");
const fixturePath = resolve(
  repoRoot,
  "agv-simulator/fixtures/dallas-layout-wcs-point-mapping-draft.json",
);
const outputPath = resolve(
  repoRoot,
  process.argv[2] || "exports/dallas-agv-layout-v2-cad.dxf",
);
const layout = JSON.parse(readFileSync(fixturePath, "utf8"));

const FT = 304.8;
const RACK_BAY_COUNT = 15;
const RACK_BAY_WIDTH_FT = 8;
const RACK_LEVEL_COUNT = 4;
const RACK_LEVEL_HEIGHT_IN = 65;
const RACK_LEVEL_HEIGHT_FT = Math.round((RACK_LEVEL_HEIGHT_IN / 12) * 100) / 100;
const GMA_PALLET_DEPTH_IN = 40;
const GMA_PALLET_DEPTH_FT = Math.round((GMA_PALLET_DEPTH_IN / 12) * 100) / 100;
const layers = [
  ["WALL", 7],
  ["EQUIP", 8],
  ["STORAGE", 3],
  ["AGV-CORRIDOR", 6],
  ["AGV-PATH", 1],
  ["STATION", 5],
  ["SAFE", 2],
  ["DOCK", 1],
  ["DIMENSION", 2],
  ["TEXT", 7],
];

const lines = [];
function pair(code, value) {
  lines.push(String(code), String(value));
}
function entity(type, layer) {
  pair(0, type);
  pair(8, layer);
}
function pt(x, y, start = 10) {
  pair(start, Math.round(x * FT * 1000) / 1000);
  pair(start + 10, Math.round(y * FT * 1000) / 1000);
  pair(start + 20, 0);
}
function line(x1, y1, x2, y2, layer = "TEXT") {
  entity("LINE", layer);
  pt(x1, y1, 10);
  pt(x2, y2, 11);
}
function rect(x, y, w, h, layer = "TEXT") {
  line(x, y, x + w, y, layer);
  line(x + w, y, x + w, y + h, layer);
  line(x + w, y + h, x, y + h, layer);
  line(x, y + h, x, y, layer);
}
function circle(x, y, r, layer = "TEXT") {
  entity("CIRCLE", layer);
  pt(x, y, 10);
  pair(40, r * FT);
}
function text(value, x, y, height = 1.2, layer = "TEXT", rotation = 0) {
  entity("TEXT", layer);
  pt(x, y, 10);
  pair(40, height * FT);
  pair(1, value);
  pair(50, rotation);
}
function arrow(x1, y1, x2, y2, layer = "AGV-PATH") {
  line(x1, y1, x2, y2, layer);
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const size = 2.2;
  const a1 = angle + Math.PI * 0.82;
  const a2 = angle - Math.PI * 0.82;
  line(x2, y2, x2 + Math.cos(a1) * size, y2 + Math.sin(a1) * size, layer);
  line(x2, y2, x2 + Math.cos(a2) * size, y2 + Math.sin(a2) * size, layer);
}
function dimension(x1, y1, x2, y2, label, vertical = false) {
  line(x1, y1, x2, y2, "DIMENSION");
  if (vertical) {
    line(x1 - 1, y1, x1 + 1, y1, "DIMENSION");
    line(x2 - 1, y2, x2 + 1, y2, "DIMENSION");
    text(label, x1 - 4, (y1 + y2) / 2, 1.1, "DIMENSION", 90);
  } else {
    line(x1, y1 - 1, x1, y1 + 1, "DIMENSION");
    line(x2, y2 - 1, x2, y2 + 1, "DIMENSION");
    text(label, (x1 + x2) / 2 - label.length * 0.35, y1 - 2, 1.1, "DIMENSION");
  }
}

function startDxf() {
  pair(0, "SECTION");
  pair(2, "HEADER");
  pair(9, "$ACADVER");
  pair(1, "AC1009");
  pair(9, "$INSUNITS");
  pair(70, 4);
  pair(0, "ENDSEC");
  pair(0, "SECTION");
  pair(2, "TABLES");
  pair(0, "TABLE");
  pair(2, "LTYPE");
  pair(70, 1);
  pair(0, "LTYPE");
  pair(2, "CONTINUOUS");
  pair(70, 0);
  pair(3, "Solid line");
  pair(72, 65);
  pair(73, 0);
  pair(40, 0);
  pair(0, "ENDTAB");
  pair(0, "TABLE");
  pair(2, "LAYER");
  pair(70, layers.length);
  for (const [name, color] of layers) {
    pair(0, "LAYER");
    pair(2, name);
    pair(70, 0);
    pair(62, color);
    pair(6, "CONTINUOUS");
  }
  pair(0, "ENDTAB");
  pair(0, "ENDSEC");
  pair(0, "SECTION");
  pair(2, "ENTITIES");
}
function endDxf() {
  pair(0, "ENDSEC");
  pair(0, "EOF");
}

function drawStorageSlots(zoneCode, x, y, zoneWidth, zoneDepth, slotW, slotD, rows, cols) {
  rect(x, y, zoneWidth, zoneDepth, "STORAGE");
  text(`${zoneCode} ${zoneWidth}ft x ${zoneDepth}ft`, x + 0.4, y + 1.6, 0.85, "TEXT");
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const sx = x + col * slotW;
      const sy = y + row * slotD;
      rect(sx, sy, slotW, slotD, "STORAGE");
      text(`${zoneCode}-${String(row + 1).padStart(2, "0")}-${String(col + 1).padStart(2, "0")}`, sx + 0.35, sy + 2.8, 0.65, "TEXT");
    }
  }
}

function drawAnnotationPanel(x, y, width, height) {
  rect(x, y, width, height, "DIMENSION");
  text("DIMENSION LEDGER", x + 3, y + height - 6, 1.5, "DIMENSION");
  text("Width: 120ft = A-CONN 12 + A 28 + B 40 + C 40", x + 3, y + height - 13, 1.05, "DIMENSION");
  text("Depth: rack-to-ABC 34ft = upper aisle 12 + storage 22", x + 3, y + height - 18, 1.05, "DIMENSION");
  text("Lower lane: 12ft outside ABC storage, not deducted", x + 3, y + height - 23, 1.05, "DIMENSION");
  text(`Rack: ${RACK_BAY_COUNT} bays x ${RACK_LEVEL_COUNT} levels = 60 storage points`, x + 3, y + height - 31, 1.05, "TEXT");
  text(`Rack level clear height: ${RACK_LEVEL_HEIGHT_IN}in (${RACK_LEVEL_HEIGHT_FT}ft)`, x + 3, y + height - 36, 1.05, "TEXT");
  text(`Rack depth: GMA pallet depth ${GMA_PALLET_DEPTH_IN}in (${GMA_PALLET_DEPTH_FT}ft)`, x + 3, y + height - 41, 1.05, "TEXT");
  text("A: 28ft x 22ft, 16 slots, each 6ft x 5ft x 9ft", x + 3, y + height - 50, 1.05, "TEXT");
  text("B: 40ft x 22ft, 16 slots, each 9ft x 5ft x 9ft", x + 3, y + height - 55, 1.05, "TEXT");
  text("C: 40ft x 22ft, 16 slots, each 9ft x 5ft x 9ft", x + 3, y + height - 60, 1.05, "TEXT");
  text("Cargo: A 68x58x100in; B/C 104x55x98in", x + 3, y + height - 68, 1.05, "TEXT");
  text("Storage points: A 16 + B 16 + C 16 + rack 60 = 108", x + 3, y + height - 73, 1.05, "TEXT");
  text("Dock doors, wait points, and chargers are WCS interfaces, not storage.", x + 3, y + height - 78, 1.05, "TEXT");
  text("AGV route centerlines stay outside floor-storage slots.", x + 3, y + height - 83, 1.05, "SAFE");
}

startDxf();

text(`${layout.layout_name} - CAD export`, 0, -8, 1.8, "TEXT");
text("Units: millimeters, geometry dimensioned in feet converted at 304.8 mm/ft", 0, -5, 1, "TEXT");
text("Draft: verify site measurements, AGV envelope, and vendor turning radius before release.", 0, -3, 1, "TEXT");

// Physical plan in feet, Y axis points down to match the reviewed planning map.
rect(0, 0, 184, 172, "WALL");
rect(0, 0, 120, 5, "EQUIP");
text(`Rack: ${RACK_BAY_COUNT} bays x ${RACK_LEVEL_COUNT} levels`, 2, 2.1, 0.85, "TEXT");
text(`Level ${RACK_LEVEL_HEIGHT_IN}in; depth ${GMA_PALLET_DEPTH_IN}in GMA`, 2, 4, 0.72, "TEXT");
for (let bay = 0; bay < RACK_BAY_COUNT; bay += 1) {
  rect(bay * RACK_BAY_WIDTH_FT, 0, RACK_BAY_WIDTH_FT, 5, "EQUIP");
}

rect(0, 5, 132, 12, "AGV-CORRIDOR");
text("Upper aisle 12ft westbound", 42, 8.2, 0.9, "TEXT");
rect(0, 5, 12, 46, "AGV-CORRIDOR");
text("A-CONN 12ft", 1.2, 29, 1, "TEXT", 90);
rect(0, 39, 132, 12, "AGV-CORRIDOR");
text("Lower lane 12ft outside storage", 44, 42.2, 0.9, "TEXT");
rect(132, 5, 40, 165, "AGV-CORRIDOR");
text("Main dock corridor 40ft x 165ft", 146, 82, 1.1, "TEXT", 90);

drawStorageSlots("A", 12, 17, 28, 22, 6, 5, 4, 4);
drawStorageSlots("B", 40, 17, 40, 22, 9, 5, 4, 4);
drawStorageSlots("C", 80, 17, 40, 22, 9, 5, 4, 4);

rect(172, 50, 12, 104, "DOCK");
text("Dock doors", 172, 47, 1, "TEXT");
for (let index = 0; index < 8; index += 1) {
  const door = 23 + index;
  rect(172, 50 + index * 13, 12, 13, "DOCK");
  text(`DOCK-${door}`, 174, 58 + index * 13, 1, "TEXT");
}

// AGV path centerlines and directions.
arrow(152, 160, 152, 14, "AGV-PATH");
arrow(152, 11, 6, 11, "AGV-PATH");
arrow(6, 11, 6, 45, "AGV-PATH");
arrow(6, 45, 152, 45, "AGV-PATH");
arrow(152, 45, 152, 160, "AGV-PATH");

for (const station of [
  ["WAIT-TOP", 128, 11],
  ["WAIT-DOCK", 152, 35],
  ["CHG-01", 140, 168],
]) {
  circle(station[1], station[2], 1.8, "STATION");
  text(station[0], station[1] + 2.5, station[2] + 0.5, 1, "STATION");
}

rect(-1, 4, 134, 48, "SAFE");
text("SAFE: route centerlines outside storage slots", 3, 54.5, 0.9, "SAFE");
drawAnnotationPanel(194, 66, 122, 104);

endDxf();

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${lines.join("\n")}\n`);
console.log(JSON.stringify({ ok: true, output: outputPath, units: "mm", source: fixturePath }, null, 2));

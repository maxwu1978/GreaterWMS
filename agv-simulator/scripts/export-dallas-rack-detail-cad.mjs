import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "../..");
const outputPath = resolve(
  repoRoot,
  process.argv[2] || "exports/dallas-rack-detail-v1-cad.dxf",
);

const FT = 304.8;
const RACK_BAY_COUNT = 15;
const RACK_BAY_WIDTH_FT = 8;
const RACK_LEVEL_COUNT = 4;
const RACK_LEVEL_HEIGHT_IN = 65;
const RACK_LEVEL_HEIGHT_FT = RACK_LEVEL_HEIGHT_IN / 12;
const RACK_TOTAL_WIDTH_FT = RACK_BAY_COUNT * RACK_BAY_WIDTH_FT;
const RACK_TOTAL_HEIGHT_FT = RACK_LEVEL_COUNT * RACK_LEVEL_HEIGHT_FT;
const GMA_PALLET_WIDTH_IN = 48;
const GMA_PALLET_DEPTH_IN = 40;
const GMA_PALLET_WIDTH_FT = GMA_PALLET_WIDTH_IN / 12;
const GMA_PALLET_DEPTH_FT = GMA_PALLET_DEPTH_IN / 12;

const layers = [
  ["EQUIP", 8],
  ["STORAGE", 3],
  ["DIMENSION", 2],
  ["TEXT", 7],
  ["SAFE", 2],
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
function text(value, x, y, height = 1.2, layer = "TEXT", rotation = 0) {
  entity("TEXT", layer);
  pt(x, y, 10);
  pair(40, height * FT);
  pair(1, value);
  pair(50, rotation);
}
function dimension(x1, y1, x2, y2, label, vertical = false) {
  line(x1, y1, x2, y2, "DIMENSION");
  if (vertical) {
    line(x1 - 1, y1, x1 + 1, y1, "DIMENSION");
    line(x2 - 1, y2, x2 + 1, y2, "DIMENSION");
    text(label, x1 - 4, (y1 + y2) / 2, 1.05, "DIMENSION", 90);
  } else {
    line(x1, y1 - 1, x1, y1 + 1, "DIMENSION");
    line(x2, y2 - 1, x2, y2 + 1, "DIMENSION");
    text(label, (x1 + x2) / 2 - label.length * 0.35, y1 - 2, 1.05, "DIMENSION");
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

function drawFrontElevation() {
  text("DAL-RACK detail - rack near office", 0, -10, 1.8, "TEXT");
  text("Front elevation: 15 bays x 4 levels, true dimensions in feet converted to mm", 0, -6.5, 1, "TEXT");
  rect(0, 0, RACK_TOTAL_WIDTH_FT, RACK_TOTAL_HEIGHT_FT, "EQUIP");

  for (let bay = 0; bay <= RACK_BAY_COUNT; bay += 1) {
    line(bay * RACK_BAY_WIDTH_FT, 0, bay * RACK_BAY_WIDTH_FT, RACK_TOTAL_HEIGHT_FT, "EQUIP");
  }
  for (let level = 0; level <= RACK_LEVEL_COUNT; level += 1) {
    line(0, level * RACK_LEVEL_HEIGHT_FT, RACK_TOTAL_WIDTH_FT, level * RACK_LEVEL_HEIGHT_FT, "EQUIP");
  }

  for (let bay = 1; bay <= RACK_BAY_COUNT; bay += 1) {
    text(`R${String(bay).padStart(2, "0")}`, (bay - 1) * RACK_BAY_WIDTH_FT + 2.2, 1.8, 0.75, "TEXT");
  }
  for (let level = 1; level <= RACK_LEVEL_COUNT; level += 1) {
    text(`L${level}`, -6.5, (level - 0.45) * RACK_LEVEL_HEIGHT_FT, 0.95, "TEXT");
  }

  dimension(0, RACK_TOTAL_HEIGHT_FT + 7, RACK_TOTAL_WIDTH_FT, RACK_TOTAL_HEIGHT_FT + 7, "Overall rack width 120ft");
  dimension(-10, 0, -10, RACK_LEVEL_HEIGHT_FT, "Level clear height 65in", true);
  dimension(-16, 0, -16, RACK_TOTAL_HEIGHT_FT, "4 levels = 260in / 21.67ft", true);
}

function drawSideProfile() {
  const x = 136;
  const y = 0;
  text("Side profile", x, -6.5, 1.2, "TEXT");
  rect(x, y, GMA_PALLET_DEPTH_FT, RACK_TOTAL_HEIGHT_FT, "EQUIP");
  for (let level = 0; level <= RACK_LEVEL_COUNT; level += 1) {
    line(x, y + level * RACK_LEVEL_HEIGHT_FT, x + GMA_PALLET_DEPTH_FT, y + level * RACK_LEVEL_HEIGHT_FT, "EQUIP");
  }
  dimension(x, RACK_TOTAL_HEIGHT_FT + 7, x + GMA_PALLET_DEPTH_FT, RACK_TOTAL_HEIGHT_FT + 7, "Depth 40in GMA");
  text("Rack depth follows GMA pallet depth", x + 8, 5, 0.9, "TEXT");
  text("Pallet footprint: 48in W x 40in D", x + 8, 9, 0.9, "TEXT");
}

function drawPalletFootprint() {
  const x = 0;
  const y = 44;
  text("GMA pallet footprint reference", x, y - 5, 1.2, "TEXT");
  rect(x, y, GMA_PALLET_WIDTH_FT, GMA_PALLET_DEPTH_FT, "STORAGE");
  dimension(x, y + GMA_PALLET_DEPTH_FT + 5, x + GMA_PALLET_WIDTH_FT, y + GMA_PALLET_DEPTH_FT + 5, "48in width");
  dimension(x + GMA_PALLET_WIDTH_FT + 5, y, x + GMA_PALLET_WIDTH_FT + 5, y + GMA_PALLET_DEPTH_FT, "40in depth", true);
  text("Use as rack depth basis; verify actual rack beam/upright spec before release.", x + 14, y + 2, 0.9, "SAFE");
}

function drawNotesPanel() {
  const x = 170;
  const y = 0;
  const width = 92;
  const height = 78;
  rect(x, y, width, height, "DIMENSION");
  text("RACK DATA", x + 3, y + height - 6, 1.5, "DIMENSION");
  text("Zone: DAL-RACK, near office", x + 3, y + height - 14, 1.05, "TEXT");
  text("Storage type: rack_storage", x + 3, y + height - 19, 1.05, "TEXT");
  text("Bays: 15, bay width: 8ft", x + 3, y + height - 24, 1.05, "TEXT");
  text("Levels: 4, clear height: 65in each", x + 3, y + height - 29, 1.05, "TEXT");
  text("Depth: GMA pallet depth 40in / 3.33ft", x + 3, y + height - 34, 1.05, "TEXT");
  text("Pallet reference: GMA 48in x 40in", x + 3, y + height - 39, 1.05, "TEXT");
  text("Storage points: 15 x 4 x 1 = 60", x + 3, y + height - 44, 1.05, "TEXT");
  text("AGV handoff remains at rack face, not inside rack.", x + 3, y + height - 52, 1.05, "SAFE");
  text("Confirm beam, upright, sprinkler and load limits on site.", x + 3, y + height - 57, 1.05, "SAFE");
}

startDxf();
drawFrontElevation();
drawSideProfile();
drawPalletFootprint();
drawNotesPanel();
endDxf();

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${lines.join("\n")}\n`);
console.log(JSON.stringify({ ok: true, output: outputPath, units: "mm" }, null, 2));

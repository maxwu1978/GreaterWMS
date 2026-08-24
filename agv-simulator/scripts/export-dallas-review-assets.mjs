import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const repoRoot = resolve(import.meta.dirname, "../..");
const fixturePath = resolve(
  repoRoot,
  "agv-simulator/fixtures/dallas-layout-wcs-point-mapping-draft.json",
);
const outputDir = resolve(repoRoot, process.argv[2] || "exports");
const layout = JSON.parse(readFileSync(fixturePath, "utf8"));

const PAGE_WIDTH = 1600;
const PAGE_HEIGHT = 1100;
const rackZone = layout.zones.find((zone) => zone.code === "DAL-RACK") || {};
const rackDimensions = rackZone.dimensions || {};
const rackBayCount = rackDimensions.bay_count || 15;
const rackBayWidthFt = rackDimensions.bay_width_ft || 8;
const rackLevelCount = rackDimensions.level_count || 4;
const rackLevelHeightIn = rackDimensions.level_clear_height_in || 65;
const rackLevelHeightFt = rackDimensions.level_clear_height_ft || 5.42;
const palletDepthIn = rackDimensions.pallet_depth_in || 40;
const palletDepthFt = rackDimensions.pallet_depth_ft || 3.33;
const palletWidthIn = rackDimensions.pallet_width_in || 48;
const rackStoragePoints = rackDimensions.storage_point_count || 60;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function rect(x, y, width, height, className, label = "") {
  return `<rect class="${className}" x="${x}" y="${y}" width="${width}" height="${height}">${label ? `<title>${escapeHtml(label)}</title>` : ""}</rect>`;
}

function line(x1, y1, x2, y2, className) {
  return `<line class="${className}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" />`;
}

function text(value, x, y, className = "label", anchor = "start", rotate = 0) {
  const transform = rotate ? ` transform="rotate(${rotate} ${x} ${y})"` : "";
  return `<text class="${className}" x="${x}" y="${y}" text-anchor="${anchor}"${transform}>${escapeHtml(value)}</text>`;
}

function arrow(x1, y1, x2, y2, className = "path-line") {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const size = 2.4;
  const left = angle + Math.PI * 0.82;
  const right = angle - Math.PI * 0.82;
  const lx = x2 + Math.cos(left) * size;
  const ly = y2 + Math.sin(left) * size;
  const rx = x2 + Math.cos(right) * size;
  const ry = y2 + Math.sin(right) * size;
  return [
    line(x1, y1, x2, y2, className),
    line(x2, y2, lx, ly, className),
    line(x2, y2, rx, ry, className),
  ].join("\n");
}

function circle(x, y, radius, className, label = "") {
  return `<circle class="${className}" cx="${x}" cy="${y}" r="${radius}">${label ? `<title>${escapeHtml(label)}</title>` : ""}</circle>`;
}

function storageSlots(zoneCode, x, y, zoneWidth, zoneDepth, slotW, slotD, rows, cols) {
  const parts = [rect(x, y, zoneWidth, zoneDepth, "storage-zone", `${zoneCode} storage`)];
  parts.push(text(`${zoneCode} ${zoneWidth}ft x ${zoneDepth}ft`, x + 1, y + 2.2, "zone-label"));
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const sx = x + col * slotW;
      const sy = y + row * slotD;
      parts.push(rect(sx, sy, slotW, slotD, "slot", `${zoneCode}-${row + 1}-${col + 1}`));
    }
  }
  return parts.join("\n");
}

function mainPlanSvg() {
  const rackBays = [];
  for (let bay = 0; bay < rackBayCount; bay += 1) {
    rackBays.push(rect(bay * rackBayWidthFt, 0, rackBayWidthFt, 5, "rack-bay"));
  }
  const docks = [];
  for (let index = 0; index < 8; index += 1) {
    const door = 23 + index;
    const y = 50 + index * 13;
    docks.push(rect(172, y, 12, 13, "dock-door", `Dock ${door}`));
    docks.push(text(`DOCK-${door}`, 178, y + 7.8, "dock-label", "middle"));
  }

  return `
    <svg class="plan-svg" viewBox="-8 -10 198 188" role="img" aria-label="Dallas AGV layout review map">
      <defs>
        <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
          <path d="M 10 0 L 0 0 0 10" class="grid-line" />
        </pattern>
      </defs>
      ${rect(-8, -10, 198, 188, "sheet-bg")}
      ${rect(0, 0, 184, 172, "wall", "Warehouse shell")}
      ${rect(0, 0, 120, 5, "rack-zone", "DAL-RACK")}
      ${rackBays.join("\n")}
      ${text(`Rack ${rackBayCount} bays x ${rackLevelCount} levels`, 2, 2, "small-label")}
      ${text(`Level ${rackLevelHeightIn}in, depth ${palletDepthIn}in GMA`, 2, 4.2, "mini-label")}

      ${rect(0, 5, 132, 12, "corridor", "Upper aisle")}
      ${text("Upper aisle 12ft westbound", 66, 12.2, "lane-label", "middle")}
      ${rect(0, 5, 12, 46, "corridor", "A connector")}
      ${text("A-CONN 12ft", 3.6, 29, "lane-label", "middle", 90)}
      ${rect(0, 39, 132, 12, "corridor", "Lower lane")}
      ${text("Lower lane 12ft outside storage", 66, 46.2, "lane-label", "middle")}
      ${rect(132, 5, 40, 165, "corridor", "Main dock corridor")}
      ${text("Main dock corridor 40ft", 150, 92, "lane-label", "middle", 90)}

      ${storageSlots("A", 12, 17, 28, 22, 6, 5, 4, 4)}
      ${storageSlots("B", 40, 17, 40, 22, 9, 5, 4, 4)}
      ${storageSlots("C", 80, 17, 40, 22, 9, 5, 4, 4)}

      ${rect(172, 50, 12, 104, "dock-zone", "Dock doors")}
      ${text("Dock doors", 178, 47, "dock-title", "middle")}
      ${docks.join("\n")}

      ${rect(-1, 5.2, 134, 46.8, "safe-outline", "Safe boundary")}
      ${arrow(152, 160, 152, 14)}
      ${arrow(152, 11, 6, 11)}
      ${arrow(6, 11, 6, 45)}
      ${arrow(6, 45, 152, 45)}
      ${arrow(152, 45, 152, 160)}

      ${circle(128, 11, 1.7, "station", "WAIT-TOP")}
      ${text("WAIT-TOP", 131, 12.4, "station-label")}
      ${circle(152, 35, 1.7, "station", "WAIT-DOCK")}
      ${text("WAIT-DOCK", 155, 36.4, "station-label")}
      ${circle(140, 168, 1.7, "station", "CHG-01")}
      ${text("CHG-01", 143, 169.4, "station-label")}
    </svg>`;
}

function rackDetailSvg() {
  const rackWidth = rackBayCount * rackBayWidthFt;
  const rackHeight = rackLevelCount * rackLevelHeightFt;
  const bayLines = [];
  for (let bay = 0; bay <= rackBayCount; bay += 1) {
    bayLines.push(line(bay * rackBayWidthFt, 0, bay * rackBayWidthFt, rackHeight, "rack-grid"));
  }
  const levelLines = [];
  for (let level = 0; level <= rackLevelCount; level += 1) {
    levelLines.push(line(0, level * rackLevelHeightFt, rackWidth, level * rackLevelHeightFt, "rack-grid"));
  }
  const bayLabels = [];
  for (let bay = 1; bay <= rackBayCount; bay += 1) {
    bayLabels.push(text(`R${String(bay).padStart(2, "0")}`, (bay - 0.5) * rackBayWidthFt, 2.1, "mini-label", "middle"));
  }
  const levelLabels = [];
  for (let level = 1; level <= rackLevelCount; level += 1) {
    levelLabels.push(text(`L${level}`, -4, (level - 0.45) * rackLevelHeightFt, "small-label", "middle"));
  }

  return `
    <svg class="rack-svg" viewBox="-24 -12 294 108" preserveAspectRatio="xMidYMin meet" role="img" aria-label="DAL-RACK detail drawing">
      ${rect(-24, -12, 294, 108, "sheet-bg")}
      ${text("Front elevation", 0, -6.5, "section-title")}
      ${rect(0, 0, rackWidth, rackHeight, "rack-zone", "Rack elevation")}
      ${bayLines.join("\n")}
      ${levelLines.join("\n")}
      ${bayLabels.join("\n")}
      ${levelLabels.join("\n")}
      ${line(0, rackHeight + 7, rackWidth, rackHeight + 7, "dimension-line")}
      ${text("Overall rack width 120ft", rackWidth / 2, rackHeight + 11, "dimension-label", "middle")}
      ${line(-10, 0, -10, rackLevelHeightFt, "dimension-line")}
      ${text("Level clear height 65in", -13, rackLevelHeightFt / 2, "dimension-label", "middle", 90)}
      ${line(-15, 0, -15, rackHeight, "dimension-line")}
      ${text("4 levels = 260in / 21.67ft", -18, rackHeight / 2, "dimension-label", "middle", 90)}

      ${text("Side profile", 136, -6.5, "section-title")}
      ${rect(136, 0, palletDepthFt, rackHeight, "rack-side", "Rack side depth")}
      ${line(136, rackHeight + 7, 136 + palletDepthFt, rackHeight + 7, "dimension-line")}
      ${text("Depth 40in GMA", 136 + palletDepthFt / 2, rackHeight + 11, "dimension-label", "middle")}
      ${text("Rack depth follows GMA pallet depth", 146, 7, "small-label")}
      ${text(`Pallet: ${palletWidthIn}in W x ${palletDepthIn}in D`, 146, 11, "small-label")}

      ${text("GMA pallet footprint", 0, 47, "section-title")}
      ${rect(0, 52, palletWidthIn / 12, palletDepthFt, "pallet", "GMA pallet")}
      ${text("48in width", 2, 61, "dimension-label")}
      ${text("40in depth", 8.5, 56, "dimension-label")}
    </svg>`;
}

function pageShell({ title, subtitle, svg, panel, source }) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    @page { size: ${PAGE_WIDTH}px ${PAGE_HEIGHT}px; margin: 0; }
    * { box-sizing: border-box; }
    html {
      width: ${PAGE_WIDTH}px;
      height: ${PAGE_HEIGHT}px;
      overflow: hidden;
    }
    body {
      width: ${PAGE_WIDTH}px;
      height: ${PAGE_HEIGHT}px;
      margin: 0;
      background: #eef2f6;
      color: #182230;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }
    .page {
      width: ${PAGE_WIDTH}px;
      height: ${PAGE_HEIGHT}px;
      overflow: hidden;
      padding: 30px 34px 24px;
      background: #f8fafc;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
      margin-bottom: 14px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 30px;
      line-height: 1.1;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 0;
      color: #475467;
      font-size: 15px;
      line-height: 1.45;
    }
    .badge {
      border: 1px solid #b2ddff;
      background: #eff8ff;
      color: #175cd3;
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }
    .content {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 390px;
      gap: 20px;
      align-items: stretch;
      height: 938px;
    }
    .canvas,
    .panel {
      border: 1px solid #d0d5dd;
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }
    .canvas {
      padding: 14px;
      min-height: 0;
      height: 100%;
      display: flex;
      align-items: center;
    }
    .panel {
      height: 100%;
      overflow: hidden;
      padding: 16px;
    }
    .panel h2 {
      margin: 0 0 10px;
      font-size: 17px;
      line-height: 1.2;
    }
    .metric {
      border-top: 1px solid #eaecf0;
      padding: 7px 0;
      display: grid;
      grid-template-columns: 96px 1fr;
      gap: 10px;
      font-size: 13px;
      line-height: 1.35;
    }
    .metric span:first-child {
      color: #667085;
      font-weight: 700;
    }
    .note {
      margin-top: 12px;
      padding: 10px;
      border-radius: 8px;
      background: #fffaeb;
      border: 1px solid #fedf89;
      color: #7a2e0e;
      font-size: 12px;
      line-height: 1.45;
    }
    footer {
      margin-top: 10px;
      color: #667085;
      font-size: 12px;
      display: flex;
      justify-content: space-between;
      gap: 20px;
    }
    svg { width: 100%; height: 100%; display: block; }
    .sheet-bg { fill: url(#grid); stroke: none; }
    .grid-line { fill: none; stroke: #e4e7ec; stroke-width: 0.15; }
    .wall { fill: #fff; stroke: #344054; stroke-width: 0.75; }
    .corridor { fill: #f4f3ff; stroke: #7a5af8; stroke-width: 0.45; }
    .safe-outline { fill: none; stroke: #eaaa08; stroke-width: 0.6; stroke-dasharray: 3 2; }
    .storage-zone { fill: #f0fdf4; stroke: #16a34a; stroke-width: 0.55; }
    .slot { fill: #dcfae6; stroke: #12b76a; stroke-width: 0.35; }
    .rack-zone, .rack-bay, .rack-side { fill: #fff7ed; stroke: #d97706; stroke-width: 0.45; }
    .dock-zone, .dock-door { fill: #fff1f3; stroke: #d92d20; stroke-width: 0.45; }
    .station { fill: #eff8ff; stroke: #175cd3; stroke-width: 0.5; }
    .path-line { stroke: #d92d20; stroke-width: 0.75; fill: none; stroke-linecap: round; }
    .pallet { fill: #ecfdf3; stroke: #079455; stroke-width: 0.45; }
    .rack-grid { stroke: #d97706; stroke-width: 0.35; fill: none; }
    .dimension-line { stroke: #ca8504; stroke-width: 0.38; fill: none; }
    .label, .zone-label, .lane-label, .dock-label, .dock-title,
    .station-label, .small-label, .mini-label, .section-title, .dimension-label {
      fill: #182230;
      dominant-baseline: middle;
      letter-spacing: 0;
    }
    .zone-label, .lane-label, .dock-title, .station-label { font-size: 2.2px; font-weight: 700; }
    .small-label { font-size: 2.1px; font-weight: 700; }
    .mini-label { font-size: 1.75px; font-weight: 700; }
    .dock-label { font-size: 1.8px; font-weight: 700; fill: #b42318; }
    .section-title { font-size: 2.8px; font-weight: 800; }
    .dimension-label { font-size: 1.9px; font-weight: 700; fill: #a15c07; }
  </style>
</head>
<body>
  <main class="page">
    <header>
      <div>
        <h1>${escapeHtml(title)}</h1>
        <p class="subtitle">${escapeHtml(subtitle)}</p>
      </div>
      <div class="badge">Customer review preview</div>
    </header>
    <section class="content">
      <div class="canvas">${svg}</div>
      <aside class="panel">${panel}</aside>
    </section>
    <footer>
      <span>Source: ${escapeHtml(source)}</span>
      <span>Draft for review: verify field measurements, AGV envelope, turning radius, rack beam/upright data, and safety clearances before release.</span>
    </footer>
  </main>
</body>
</html>`;
}

function mainPanel() {
  return `
    <h2>Review ledger</h2>
    <div class="metric"><span>Warehouse</span><strong>Dallas AGV standard layout v2</strong></div>
    <div class="metric"><span>Width split</span><strong>A-CONN 12ft + A 28ft + B 40ft + C 40ft = 120ft</strong></div>
    <div class="metric"><span>Depth split</span><strong>Upper aisle 12ft + floor storage 22ft = 34ft rack-to-ABC</strong></div>
    <div class="metric"><span>Lower lane</span><strong>12ft outside ABC storage, not deducted from storage depth</strong></div>
    <div class="metric"><span>A storage</span><strong>28ft x 22ft, 16 slots, each 6ft x 5ft x 9ft</strong></div>
    <div class="metric"><span>B storage</span><strong>40ft x 22ft, 16 slots, each 9ft x 5ft x 9ft</strong></div>
    <div class="metric"><span>C storage</span><strong>40ft x 22ft, 16 slots, each 9ft x 5ft x 9ft</strong></div>
    <div class="metric"><span>Rack</span><strong>${rackBayCount} bays x ${rackLevelCount} levels, ${rackStoragePoints} storage points</strong></div>
    <div class="metric"><span>Rack height</span><strong>${rackLevelHeightIn}in clear height per level</strong></div>
    <div class="metric"><span>Rack depth</span><strong>GMA pallet depth ${palletDepthIn}in / ${palletDepthFt}ft</strong></div>
    <div class="metric"><span>WCS draft</span><strong>108 storage + 8 dock + 3 station/buffer = 119 points</strong></div>
    <div class="note">Dock doors, wait points, chargers, drive aisles, A-CONN, and ABC-LOWER are transport/interface areas, not WMS storage locations.</div>`;
}

function rackPanel() {
  return `
    <h2>Rack data</h2>
    <div class="metric"><span>Zone</span><strong>DAL-RACK near office</strong></div>
    <div class="metric"><span>Storage type</span><strong>rack_storage</strong></div>
    <div class="metric"><span>Bays</span><strong>${rackBayCount} bays, ${rackBayWidthFt}ft each</strong></div>
    <div class="metric"><span>Levels</span><strong>${rackLevelCount} levels</strong></div>
    <div class="metric"><span>Clear height</span><strong>${rackLevelHeightIn}in / ${rackLevelHeightFt}ft per level</strong></div>
    <div class="metric"><span>Depth basis</span><strong>GMA pallet depth ${palletDepthIn}in / ${palletDepthFt}ft</strong></div>
    <div class="metric"><span>Pallet</span><strong>GMA ${palletWidthIn}in x ${palletDepthIn}in</strong></div>
    <div class="metric"><span>Count</span><strong>${rackBayCount} x ${rackLevelCount} x 1 = ${rackStoragePoints} rack storage points</strong></div>
    <div class="metric"><span>AGV handoff</span><strong>At rack face only; AGV does not enter rack structure</strong></div>
    <div class="note">Before release, verify beam capacity, upright depth, sprinkler clearance, overhang policy, and actual rack vendor spec on site.</div>`;
}

async function browserFromFrontend() {
  const playwrightPath = resolve(repoRoot, "frontend/node_modules/playwright/index.mjs");
  const { chromium } = await import(pathToFileURL(playwrightPath).href);
  try {
    return await chromium.launch({ headless: true });
  } catch (error) {
    try {
      return await chromium.launch({ channel: "chrome", headless: true });
    } catch {
      throw error;
    }
  }
}

async function exportHtmlToReviewAssets(browser, htmlPath, pngPath, pdfPath) {
  const page = await browser.newPage({
    viewport: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
    deviceScaleFactor: 2,
  });
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
  await page.screenshot({ path: pngPath, fullPage: false });
  await page.pdf({
    path: pdfPath,
    printBackground: true,
    preferCSSPageSize: true,
    width: `${PAGE_WIDTH}px`,
    height: `${PAGE_HEIGHT}px`,
    margin: { top: "0px", right: "0px", bottom: "0px", left: "0px" },
  });
  await page.close();
}

async function main() {
  mkdirSync(outputDir, { recursive: true });
  const mainHtmlPath = resolve(outputDir, "dallas-agv-layout-v2-review.html");
  const mainPngPath = resolve(outputDir, "dallas-agv-layout-v2-review.png");
  const mainPdfPath = resolve(outputDir, "dallas-agv-layout-v2-review.pdf");
  const rackHtmlPath = resolve(outputDir, "dallas-rack-detail-v1-review.html");
  const rackPngPath = resolve(outputDir, "dallas-rack-detail-v1-review.png");
  const rackPdfPath = resolve(outputDir, "dallas-rack-detail-v1-review.pdf");

  writeFileSync(
    mainHtmlPath,
    pageShell({
      title: "Dallas AGV Layout v2",
      subtitle: "Customer review preview for floor storage, AGV lanes, dock interfaces, route direction, and rack summary.",
      svg: mainPlanSvg(),
      panel: mainPanel(),
      source: "exports/dallas-agv-layout-v2-cad.dxf",
    }),
  );
  writeFileSync(
    rackHtmlPath,
    pageShell({
      title: "DAL-RACK Detail",
      subtitle: "Customer review preview for the office-side rack: bay count, level height, GMA depth, and storage-point count.",
      svg: rackDetailSvg(),
      panel: rackPanel(),
      source: "exports/dallas-rack-detail-v1-cad.dxf",
    }),
  );

  const browser = await browserFromFrontend();
  try {
    await exportHtmlToReviewAssets(browser, mainHtmlPath, mainPngPath, mainPdfPath);
    await exportHtmlToReviewAssets(browser, rackHtmlPath, rackPngPath, rackPdfPath);
  } finally {
    await browser.close();
  }

  console.log(
    JSON.stringify(
      {
        ok: true,
        output_dir: outputDir,
        files: [
          mainHtmlPath,
          mainPngPath,
          mainPdfPath,
          rackHtmlPath,
          rackPngPath,
          rackPdfPath,
        ],
      },
      null,
      2,
    ),
  );
}

await main();

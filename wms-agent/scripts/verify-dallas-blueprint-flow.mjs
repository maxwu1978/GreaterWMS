import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const agentRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(agentRoot, "..");
const exportsDir = path.join(repoRoot, "exports");
const htmlPath = path.join(agentRoot, "local_agent", "static", "index.html");
const fixturePath = path.join(repoRoot, "agv-simulator", "fixtures", "dallas-layout-wcs-point-mapping-draft.json");
const layoutReviewPath = path.join(exportsDir, "dallas-agv-layout-v2-review.html");
const rackReviewPath = path.join(exportsDir, "dallas-rack-detail-v1-review.html");
const payloadOutPath = path.join(exportsDir, "dallas-local-agent-blueprint-draft.json");
const screenshotOutPath = path.join(exportsDir, "dallas-local-agent-blueprint-review.png");
const playwrightModule = path.join(repoRoot, "frontend", "node_modules", "playwright", "index.mjs");

const { chromium } = await import(pathToFileURL(playwrightModule).href);

function assertCondition(condition, message, details = undefined) {
  if (!condition) {
    const error = new Error(message);
    if (details !== undefined) error.details = details;
    throw error;
  }
}

function countBy(items, keyFn) {
  return items.reduce((counts, item) => {
    const key = keyFn(item);
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function numericEquals(actual, expected, label) {
  assertCondition(Number(actual) === expected, `${label} expected ${expected}, got ${actual}`);
}

function zoneByCode(payload, code) {
  const zone = payload.zones.find((item) => item.code === code);
  assertCondition(zone, `Missing zone ${code}`);
  return zone;
}

function locationCount(zone) {
  return Array.isArray(zone.locations) ? zone.locations.length : 0;
}

function validateZoneDimensions(zone, expected) {
  Object.entries(expected).forEach(([key, value]) => {
    numericEquals(zone.dimensions?.[key] ?? zone[key], value, `${zone.code}.${key}`);
  });
}

async function runBlueprintFlow() {
  await mkdir(exportsDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 }, deviceScaleFactor: 1 });

  try {
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "domcontentloaded" });
    await page.evaluate(() => {
      document.querySelector("#loginPanel")?.classList.add("hidden");
      document.querySelector("#agentPanel")?.classList.remove("hidden");
      window.showBlueprintPanel?.();
    });
    const placeholder = await page.locator("#blueprintDescription").getAttribute("placeholder");
    assertCondition(placeholder?.includes("DAL-A"), "Dallas blueprint placeholder is missing structured DAL-A data.");
    await page.locator("#blueprintDescription").fill(placeholder);
    await page.locator("#generateBlueprintBtn").click();
    await page.waitForFunction(() => Boolean(window.blueprintDraftPayload?.().zones?.length));

    const result = await page.evaluate(() => {
      const payload = window.blueprintDraftPayload();
      const validation = window.validateBlueprintWcsDraftPayload(payload);
      return {
        payload,
        validation,
        subtitle: document.querySelector("#blueprintSubtitle")?.textContent || "",
        detailText: document.querySelector("#blueprintDetail")?.textContent || "",
      };
    });

    await page.locator("#blueprintPanel").screenshot({ path: screenshotOutPath });
    return result;
  } finally {
    await browser.close();
  }
}

const [fixtureText, layoutReviewHtml, rackReviewHtml, flow] = await Promise.all([
  readFile(fixturePath, "utf8"),
  readFile(layoutReviewPath, "utf8"),
  readFile(rackReviewPath, "utf8"),
  runBlueprintFlow(),
]);

const fixture = JSON.parse(fixtureText);
const { payload, validation, subtitle } = flow;
const zoneCodes = payload.zones.map((zone) => zone.code);
const fixtureZoneCodes = fixture.zones.map((zone) => zone.code);
const missingFixtureZones = fixtureZoneCodes.filter((code) => !zoneCodes.includes(code));
const fakeZoneCodes = zoneCodes.filter((code) => code === "DALLAS-WAREHOUSE-FROM-DRAWING" || code.startsWith("LEFT-WEST-SIDE"));
const totalLocations = payload.zones.reduce((sum, zone) => sum + locationCount(zone), 0);
const roleCounts = countBy(payload.wcs_point_mapping_draft, (mapping) => mapping.point_role);
const stationCodes = payload.stations.map((station) => station.code);

assertCondition(validation.ok, "Local agent WCS draft validation failed.", validation);
assertCondition(payload.warehouse.code === "DAL", `Expected warehouse code DAL, got ${payload.warehouse.code}`);
assertCondition(missingFixtureZones.length === 0, "Local agent draft is missing fixture zone codes.", missingFixtureZones);
assertCondition(fakeZoneCodes.length === 0, "Local agent parser created zones from narrative text.", fakeZoneCodes);
numericEquals(payload.zones.length, 9, "payload.zones.length");
numericEquals(totalLocations, 108, "generated storage location count");
numericEquals(payload.wcs_point_mapping_draft.length, 119, "WCS draft point count");
numericEquals(roleCounts.storage || 0, 108, "storage WCS point count");
numericEquals(roleCounts.dock || 0, 8, "dock WCS point count");
numericEquals(roleCounts.buffer || 0, 2, "buffer WCS point count");
numericEquals(roleCounts.agv_station || 0, 1, "AGV station WCS point count");
assertCondition(["WAIT-TOP", "WAIT-DOCK", "CHG-01"].every((code) => stationCodes.includes(code)), "Missing AGV station code.", stationCodes);

const rack = zoneByCode(payload, "DAL-RACK");
validateZoneDimensions(rack, {
  pallet_width_in: 48,
  pallet_depth_in: 40,
  level_clear_height_in: 65,
  bay_count: 15,
  bay_width_ft: 8,
});
numericEquals(locationCount(rack), 60, "DAL-RACK location count");

const dalA = zoneByCode(payload, "DAL-A");
validateZoneDimensions(dalA, {
  width_ft: 6,
  depth_ft: 5,
  height_ft: 9,
  zone_width_ft: 28,
  zone_depth_ft: 22,
});
numericEquals(locationCount(dalA), 16, "DAL-A location count");

["DAL-B", "DAL-C"].forEach((code) => {
  const zone = zoneByCode(payload, code);
  validateZoneDimensions(zone, {
    width_ft: 9,
    depth_ft: 5,
    height_ft: 9,
    zone_width_ft: 40,
    zone_depth_ft: 22,
  });
  numericEquals(locationCount(zone), 16, `${code} location count`);
});

["A-CONN", "TOP-AISLE", "ABC-LOWER", "DRV", "DOCK"].forEach((code) => {
  numericEquals(locationCount(zoneByCode(payload, code)), 0, `${code} generated location count`);
});
assertCondition(payload.route_policy.dock_doors_are_storage_locations === false, "Dock doors must remain transport interfaces, not storage.");
assertCondition(subtitle.includes("108 draft locations"), "Blueprint summary should show 108 draft locations.", subtitle);
assertCondition(layoutReviewHtml.includes("108 storage + 8 dock + 3 station/buffer = 119 points"), "Review layout summary does not match WCS count.");
assertCondition(rackReviewHtml.includes("65in") && rackReviewHtml.includes("GMA"), "Rack review artifact does not show 65in/GMA rack details.");

await writeFile(payloadOutPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

const summary = {
  ok: true,
  generated_payload: payloadOutPath,
  screenshot: screenshotOutPath,
  warehouse: payload.warehouse,
  zones: zoneCodes,
  generated_locations: totalLocations,
  wcs_points: payload.wcs_point_mapping_draft.length,
  role_counts: roleCounts,
  stations: stationCodes,
  validation_summary: validation.summary,
};

console.log(JSON.stringify(summary, null, 2));

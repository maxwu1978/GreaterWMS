import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Boxes, CheckCircle2, ChevronLeft, Radar } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchSetupProgress, runQuickSetup } from "../../shared/api/setup";
import { queryKeys } from "../../shared/api/queryKeys";
import { useI18n } from "../../shared/i18n";
import PasswordInput from "../../shared/components/PasswordInput";

type UnitSystem = "metric" | "imperial";

const METERS_TO_FEET = 3.28084;
const KG_TO_LB = 2.20462;

const toDisplayLength = (meters: number, unitSystem: UnitSystem) =>
  unitSystem === "imperial" ? meters * METERS_TO_FEET : meters;

const fromDisplayLength = (value: number, unitSystem: UnitSystem) =>
  unitSystem === "imperial" ? value / METERS_TO_FEET : value;

const toDisplayWeight = (kg: number, unitSystem: UnitSystem) =>
  unitSystem === "imperial" ? kg * KG_TO_LB : kg;

const fromDisplayWeight = (value: number, unitSystem: UnitSystem) =>
  unitSystem === "imperial" ? value / KG_TO_LB : value;

const lengthUnitLabel = (unitSystem: UnitSystem) => (unitSystem === "imperial" ? "ft" : "m");
const weightUnitLabel = (unitSystem: UnitSystem) => (unitSystem === "imperial" ? "lb" : "kg");

const buildLevelProfiles = (count: number, fallbackHeight = 1.5, fallbackCapacity = 1200, fallbackPositions = 5) =>
  Array.from({ length: Math.max(count, 1) }, (_, index) => ({
    level: index + 1,
    height_m: fallbackHeight,
    capacity_kg: fallbackCapacity,
    positions_count: fallbackPositions,
  }));

const stepIndexByName: Record<string, number> = {
  warehouse: 0,
  locations: 1,
  client: 2,
  skus: 3,
  billing: 4,
  team: 5,
};

export default function SetupWizardPage() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState(0);
  const [unitSystem, setUnitSystem] = useState<UnitSystem>("metric");
  const [answers, setAnswers] = useState<Record<string, any>>({
    warehouse_name: "",
    timezone: "America/Chicago",
    aisles: 3,
    racks_per_aisle: 4,
    levels: 3,
    agv_accessible: false,
    aisle_width_m: 3.2,
    level_height_m: 1.5,
    level_capacity_kg: 1200,
    positions_per_level: 5,
    level_profiles: buildLevelProfiles(3, 1.5, 1200, 5),
    client_name: "",
    client_email: "",
    client_portal_email: "",
    client_portal_password: "",
    skus: [{ sku_code: "", name: "" }],
    storage_rate: 0.85,
    minimum_monthly: 200,
    team_members: [{ email: "", name: "", password: "welcome123" }],
  });
  const [result, setResult] = useState<any>(null);

  const { data: progress } = useQuery({
    queryKey: queryKeys.setup.progress(),
    queryFn: fetchSetupProgress,
  });

  const quickSetup = useMutation({
    mutationFn: (data: any) => runQuickSetup(data),
    onSuccess: (resp) => setResult(resp.data),
  });

  useEffect(() => {
    const requestedStep = searchParams.get("step");
    if (!requestedStep) return;
    const target = stepIndexByName[requestedStep];
    if (target !== undefined) {
      setStep(target);
    }
  }, [searchParams]);

  useEffect(() => {
    setAnswers((current: Record<string, any>) => {
      const existing = Array.isArray(current.level_profiles) ? current.level_profiles : [];
      const nextProfiles = Array.from({ length: Math.max(current.levels || 1, 1) }, (_, index) => {
        const found = existing[index];
        return {
          level: index + 1,
          height_m: found?.height_m ?? current.level_height_m ?? 1.5,
          capacity_kg: found?.capacity_kg ?? current.level_capacity_kg ?? 1200,
          positions_count: found?.positions_count ?? current.positions_per_level ?? 5,
        };
      });
      return { ...current, level_profiles: nextProfiles };
    });
  }, [answers.levels, answers.level_height_m, answers.level_capacity_kg, answers.positions_per_level]);

  const steps = [
    {
      key: "warehouse",
      title: t("setup.warehouseTitle", "Your warehouse"),
      icon: "🏭",
      description: t("setup.warehouseBody", "Start with the physical shell: warehouse name and operating timezone."),
      fields: (
        <div className="space-y-4">
          <Field
            label={t("setup.warehouseName", "What is your warehouse called?")}
            value={answers.warehouse_name}
            onChange={(v) => setAnswers({ ...answers, warehouse_name: v })}
            placeholder={t("setup.warehouseNamePlaceholder", "e.g. DFW Warehouse #1")}
          />
          <Field
            label={t("setup.timezone", "Timezone")}
            value={answers.timezone}
            onChange={(v) => setAnswers({ ...answers, timezone: v })}
            type="select"
            options={["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"]}
          />
        </div>
      ),
    },
    {
      key: "locations",
      title: t("setup.layoutTitle", "Shelf layout"),
      icon: "📐",
      description: t("setup.layoutBody", "Define the first aisle-rack-level pattern so the system can generate a believable location skeleton."),
      fields: (
        <div className="space-y-4">
          <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4">
            <p className="text-sm font-semibold text-[#13212c]">{t("setup.unitSystem", "Unit system")}</p>
            <div className="mt-3 inline-flex rounded-full border border-[#13212c]/10 bg-white p-1">
              {(["metric", "imperial"] as UnitSystem[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setUnitSystem(option)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    unitSystem === option
                      ? "bg-[#13212c] text-[#f4efe8]"
                      : "text-[#61717d] hover:text-[#13212c]"
                  }`}
                >
                  {option === "metric"
                    ? t("common.metricSystem", "Metric (EU)")
                    : t("common.imperialSystem", "Imperial (US)")}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <NumberField label={t("setup.aisles", "Aisles")} value={answers.aisles} onChange={(v) => setAnswers({ ...answers, aisles: v })} />
            <NumberField
              label={t("setup.racksPerAisle", "Racks per aisle")}
              value={answers.racks_per_aisle}
              onChange={(v) => setAnswers({ ...answers, racks_per_aisle: v })}
            />
            <NumberField label={t("setup.levels", "Levels high")} value={answers.levels} onChange={(v) => setAnswers({ ...answers, levels: v })} />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <NumberField
              label={t("setup.positionsPerLevel", "Default positions per level")}
              value={answers.positions_per_level}
              onChange={(v) => setAnswers({ ...answers, positions_per_level: v })}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <NumberField
              label={`${t("setup.aisleWidth", "Aisle width")} (${lengthUnitLabel(unitSystem)})`}
              value={toDisplayLength(answers.aisle_width_m, unitSystem)}
              onChange={(v) => setAnswers({ ...answers, aisle_width_m: fromDisplayLength(v, unitSystem) })}
              step={0.1}
            />
            <NumberField
              label={`${t("setup.levelHeight", "Per-level rack height")} (${lengthUnitLabel(unitSystem)})`}
              value={toDisplayLength(answers.level_height_m, unitSystem)}
              onChange={(v) => setAnswers({ ...answers, level_height_m: fromDisplayLength(v, unitSystem) })}
              step={0.1}
            />
            <NumberField
              label={`${t("setup.levelCapacity", "Per-level rack capacity")} (${weightUnitLabel(unitSystem)})`}
              value={toDisplayWeight(answers.level_capacity_kg, unitSystem)}
              onChange={(v) => setAnswers({ ...answers, level_capacity_kg: fromDisplayWeight(v, unitSystem) })}
              step={50}
            />
          </div>
          <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4">
            <p className="text-sm font-semibold text-[#13212c]">{t("setup.levelProfiles", "Per-level rack profile")}</p>
            <p className="mt-1 text-sm leading-6 text-[#61717d]">
              {t("setup.levelProfilesBody", "Each level can have a different clear height and load rating. Enter the real profile operators and AGV planning must respect.")}
            </p>
            <div className="mt-4 space-y-3">
              {answers.level_profiles.map((profile: any, index: number) => (
                <div key={index} className="grid gap-3 md:grid-cols-[120px_1fr_1fr_1fr]">
                  <div className="rounded-2xl border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-sm font-semibold text-[#13212c]">
                    {t("setup.levelLabel", "Level {level}", { level: profile.level })}
                  </div>
                  <NumberField
                    label={`${t("setup.levelHeightSingle", "Height")} (${lengthUnitLabel(unitSystem)})`}
                    value={toDisplayLength(profile.height_m, unitSystem)}
                    onChange={(v) =>
                      setAnswers({
                        ...answers,
                        level_profiles: answers.level_profiles.map((item: any, itemIndex: number) =>
                          itemIndex === index ? { ...item, height_m: fromDisplayLength(v, unitSystem) } : item,
                        ),
                      })
                    }
                    step={0.1}
                  />
                  <NumberField
                    label={`${t("setup.levelCapacitySingle", "Capacity")} (${weightUnitLabel(unitSystem)})`}
                    value={toDisplayWeight(profile.capacity_kg, unitSystem)}
                    onChange={(v) =>
                      setAnswers({
                        ...answers,
                        level_profiles: answers.level_profiles.map((item: any, itemIndex: number) =>
                          itemIndex === index ? { ...item, capacity_kg: fromDisplayWeight(v, unitSystem) } : item,
                        ),
                      })
                    }
                    step={50}
                  />
                  <NumberField
                    label={t("setup.levelPositionsSingle", "Positions")}
                    value={profile.positions_count}
                    onChange={(v) =>
                      setAnswers({
                        ...answers,
                        level_profiles: answers.level_profiles.map((item: any, itemIndex: number) =>
                          itemIndex === index ? { ...item, positions_count: v } : item,
                        ),
                      })
                    }
                  />
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            {t("setup.layoutSummary", "This will create {count} storage locations plus 1 dock.", {
              count:
                answers.aisles *
                answers.racks_per_aisle *
                (answers.level_profiles || []).reduce((sum: number, profile: any) => sum + Number(profile.positions_count || 0), 0),
            })}
          </div>
          <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4 text-sm leading-6 text-[#61717d]">
            {t("setup.layoutPhysicsSummary", "Planned clear aisle width: {aisle} {lengthUnit}. Total rack height: {height} {lengthUnit}. Per-level capacity: {capacity} {weightUnit}.", {
              aisle: Number(toDisplayLength(answers.aisle_width_m || 0, unitSystem)).toFixed(1),
              height: Number(
                toDisplayLength(
                  (answers.level_profiles || []).reduce((sum: number, profile: any) => sum + Number(profile.height_m || 0), 0),
                  unitSystem,
                ),
              ).toFixed(1),
              capacity: Number(
                toDisplayWeight(
                  Math.min(...((answers.level_profiles || []).map((profile: any) => Number(profile.capacity_kg || 0)).filter(Boolean) || [0])),
                  unitSystem,
                ),
              ).toFixed(0),
              lengthUnit: lengthUnitLabel(unitSystem),
              weightUnit: weightUnitLabel(unitSystem),
            })}
          </div>
          <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#8db6ff]/20 bg-[#8db6ff]/10 px-4 py-4">
            <input
              type="checkbox"
              checked={answers.agv_accessible}
              onChange={(e) => setAnswers({ ...answers, agv_accessible: e.target.checked })}
              className="mt-1 h-5 w-5 accent-[#13212c]"
            />
            <div>
              <p className="text-sm font-semibold text-[#13212c]">{t("setup.agvReady", "AGV-ready locations")}</p>
              <p className="mt-1 text-sm leading-6 text-[#61717d]">
                {t("setup.agvReadyBody", "Turn this on if you want the first location layout to reserve AGV-capable routing context for later automation work.")}
              </p>
            </div>
          </label>
        </div>
      ),
    },
    {
      key: "client",
      title: t("setup.clientTitle", "First client"),
      icon: "👤",
      description: t("setup.clientBody", "Anchor the workspace to a real customer account before you load products or transactions."),
      fields: (
        <div className="space-y-4">
          <Field
            label={t("setup.clientCompany", "Client company name")}
            value={answers.client_name}
            onChange={(v) => setAnswers({ ...answers, client_name: v })}
            placeholder={t("setup.clientCompanyPlaceholder", "e.g. Acme Pet Supplies")}
          />
          <Field
            label={t("setup.clientEmail", "Client email")}
            value={answers.client_email}
            onChange={(v) => setAnswers({ ...answers, client_email: v })}
            placeholder={t("setup.clientEmailPlaceholder", "ops@acme.com")}
          />
          <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4">
            <p className="text-sm font-semibold text-[#13212c]">{t("setup.portalLogin", "Client portal login (optional)")}</p>
            <p className="mt-1 text-sm leading-6 text-[#61717d]">
              {t("setup.portalLoginBody", "Add this now if the client should log in during the trial. Leave it empty if portal access will come later.")}
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <Field
                label={t("setup.portalEmail", "Portal email")}
                value={answers.client_portal_email}
                onChange={(v) => setAnswers({ ...answers, client_portal_email: v })}
                placeholder={t("setup.portalEmailPlaceholder", "portal@acme.com")}
              />
              <Field
                label={t("setup.portalPassword", "Portal password")}
                value={answers.client_portal_password}
                onChange={(v) => setAnswers({ ...answers, client_portal_password: v })}
                type="password"
              />
            </div>
          </div>
        </div>
      ),
    },
    {
      key: "skus",
      title: t("setup.skusTitle", "Products (SKUs)"),
      icon: "📦",
      description: t("setup.skusBody", "Create a few live SKUs now so receiving and inventory have something real to operate on."),
      fields: (
        <div className="space-y-3">
          {answers.skus.map((sku: any, i: number) => (
            <div key={i} className="grid gap-3 md:grid-cols-2">
              <input
                className="rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                placeholder={t("setup.skuCode", "SKU code")}
                value={sku.sku_code}
                onChange={(e) => {
                  const s = [...answers.skus];
                  s[i] = { ...s[i], sku_code: e.target.value };
                  setAnswers({ ...answers, skus: s });
                }}
              />
              <input
                className="rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                placeholder={t("setup.productName", "Product name")}
                value={sku.name}
                onChange={(e) => {
                  const s = [...answers.skus];
                  s[i] = { ...s[i], name: e.target.value };
                  setAnswers({ ...answers, skus: s });
                }}
              />
            </div>
          ))}
          <button
            type="button"
            onClick={() => setAnswers({ ...answers, skus: [...answers.skus, { sku_code: "", name: "" }] })}
            className="text-sm font-medium text-[#13212c]"
          >
            {t("setup.addSku", "+ Add another SKU")}
          </button>
        </div>
      ),
    },
    {
      key: "billing",
      title: t("setup.billingTitle", "Billing rates"),
      icon: "💰",
      description: t("setup.billingBody", "Set the first commercial defaults so the trial can connect warehouse activity to a believable billing story."),
      fields: (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <NumberField
              label={t("setup.storageRate", "Storage $/pallet/day")}
              value={answers.storage_rate}
              onChange={(v) => setAnswers({ ...answers, storage_rate: v })}
              step={0.05}
            />
            <NumberField
              label={t("setup.minimumMonthly", "Minimum monthly $")}
              value={answers.minimum_monthly}
              onChange={(v) => setAnswers({ ...answers, minimum_monthly: v })}
              step={50}
            />
          </div>
          <p className="text-sm leading-6 text-[#61717d]">
            {t("setup.billingFootnote", "You can customize rates per client later. These values simply establish the first default commercial policy.")}
          </p>
        </div>
      ),
    },
    {
      key: "team",
      title: t("setup.teamTitle", "Your team"),
      icon: "👥",
      description: t("setup.teamBody", "Add the first warehouse staff so the trial can move beyond a single admin login."),
      fields: (
        <div className="space-y-3">
          {answers.team_members.map((member: any, i: number) => (
            <div key={i} className="grid gap-3 md:grid-cols-2">
              <input
                className="rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                placeholder={t("setup.teamName", "Name")}
                value={member.name}
                onChange={(e) => {
                  const team = [...answers.team_members];
                  team[i] = { ...team[i], name: e.target.value };
                  setAnswers({ ...answers, team_members: team });
                }}
              />
              <input
                className="rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                placeholder={t("setup.teamEmail", "Email")}
                value={member.email}
                onChange={(e) => {
                  const team = [...answers.team_members];
                  team[i] = { ...team[i], email: e.target.value };
                  setAnswers({ ...answers, team_members: team });
                }}
              />
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              setAnswers({
                ...answers,
                team_members: [...answers.team_members, { email: "", name: "", password: "welcome123" }],
              })
            }
            className="text-sm font-medium text-[#13212c]"
          >
            {t("setup.addTeamMember", "+ Add team member")}
          </button>
        </div>
      ),
    },
  ];

  const setupStepLabel = (stepName: string) => {
    const map: Record<string, string> = {
      warehouse: t("setup.warehouseTitle", "Your warehouse"),
      locations: t("setup.layoutTitle", "Shelf layout"),
      client: t("setup.clientTitle", "First client"),
      skus: t("setup.skusTitle", "Products (SKUs)"),
      billing: t("setup.billingTitle", "Billing rates"),
      team: t("setup.teamTitle", "Your team"),
    };
    return map[stepName] || stepName;
  };

  const currentStep = steps[step];
  const completedCount = progress?.completed || 0;
  const totalCount = progress?.total || steps.length;
  const percent = Math.round((completedCount / Math.max(totalCount, 1)) * 100);

  const summary = useMemo(
    () => ({
      locations:
        answers.aisles *
        answers.racks_per_aisle *
        (answers.level_profiles || []).reduce((sum: number, profile: any) => sum + Number(profile.positions_count || 0), 0),
      skuCount: answers.skus.filter((s: any) => s.sku_code || s.name).length,
      teamCount: answers.team_members.filter((m: any) => m.email || m.name).length,
    }),
    [answers],
  );

  const handleFinish = () => {
    const data: any = { ...answers };
    data.skus = answers.skus.filter((s: any) => s.sku_code && s.name);
    data.team_members = answers.team_members.filter((m: any) => m.email && m.name);
    if (!data.client_name) {
      delete data.client_name;
      delete data.skus;
    }
    quickSetup.mutate(data);
  };

  if (result) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 py-6">
        <section className="rounded-[2rem] border border-[#13212c]/10 bg-white/85 p-8 text-center shadow-[0_24px_60px_rgba(19,33,44,0.08)]">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-emerald-600">
            <CheckCircle2 size={28} />
          </div>
          <h1 className="mt-5 text-3xl font-semibold tracking-[-0.03em] text-[#13212c]">
            {t("setup.readyTitle", "Your warehouse is ready")}
          </h1>
          <p className="mt-3 text-sm leading-7 text-[#61717d]">
            {t(
              "setup.readyBody",
              "The starter warehouse structure, client profile, SKU master data, and team baseline are now in place."
            )}
          </p>
        </section>

        <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] text-left text-sm space-y-2">
          {result.steps_completed?.map((s: string) => (
            <div key={s} className="flex items-center gap-2">
              <span className="text-green-500">✓</span>
              <span>{setupStepLabel(s)}</span>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <Link
            to="/dashboard"
            className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-6 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040]"
          >
            {t("setup.goDashboard", "Go to dashboard")}
            <ArrowRight size={16} />
          </Link>
          <Link
            to="/migration"
            className="inline-flex items-center justify-center gap-2 rounded-full border border-[#13212c]/12 bg-white px-6 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:border-[#13212c]/24"
          >
            {t("setup.openMigration", "Bring over existing data")}
            <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    );
  }

  if (progress?.all_done) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 py-6">
        <section className="rounded-[2rem] border border-[#13212c]/10 bg-white/85 p-8 text-center shadow-[0_24px_60px_rgba(19,33,44,0.08)]">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-emerald-600">
            <CheckCircle2 size={28} />
          </div>
          <h1 className="mt-5 text-3xl font-semibold tracking-[-0.03em] text-[#13212c]">
            {t("setup.completeTitle", "Setup complete")}
          </h1>
          <p className="mt-3 text-sm leading-7 text-[#61717d]">
            {t("setup.completeBody", "Your warehouse is fully configured and ready for live work.")}
          </p>
        </section>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/dashboard"
            className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-6 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040]"
          >
            {t("setup.goDashboard", "Go to dashboard")}
            <ArrowRight size={16} />
          </Link>
          <Link
            to="/migration"
            className="inline-flex items-center justify-center gap-2 rounded-full border border-[#13212c]/12 bg-white px-6 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:border-[#13212c]/24"
          >
            {t("setup.openMigrationStep", "Open migration step")}
            <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_360px]">
        <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_58%,#253847_100%)] p-6 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-full border border-white/12 bg-white/5">
                <Boxes size={18} />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-[#9eb2bf]">{t("setup.onboarding", "Onboarding")}</p>
                <p className="font-semibold">{t("nav.setupWizard", "Setup Wizard")}</p>
              </div>
            </div>
            <span className="rounded-full border border-[#f7bf45]/30 bg-[#f7bf45]/12 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#f7bf45]">
              {t("setup.stepOf", "Step {step} of {total}", { step: step + 1, total: steps.length })}
            </span>
          </div>

          <h1 className="mt-6 text-4xl font-semibold tracking-[-0.03em]">
            {t("setup.heroTitle", "Build the first workable warehouse environment before operators touch live stock.")}
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-[#c2d0d8]">
            {t(
              "setup.heroBody",
              "This wizard turns a blank trial into a usable workspace with warehouse structure, client setup, SKU data, billing defaults, and operator logins.",
            )}
          </p>

          <div className="mt-6 flex gap-1">
            {steps.map((item, i) => (
              <div key={item.key} className={`h-2 flex-1 rounded-full ${i <= step ? "bg-[#f7bf45]" : "bg-white/10"}`} />
            ))}
          </div>

          <div className="mt-6 grid gap-3 md:grid-cols-3">
            <WizardSignal
              label={t("setup.signalWarehouse", "Warehouse")}
              value={progress?.steps?.find((s: any) => s.name === "warehouse")?.done ? t("setup.done", "Done") : t("setup.pending", "Pending")}
            />
            <WizardSignal
              label={t("setup.signalClientSkus", "Client + SKUs")}
              value={progress?.steps?.find((s: any) => s.name === "client")?.done ? t("setup.started", "Started") : t("setup.pending", "Pending")}
            />
            <WizardSignal
              label={t("setup.signalTeam", "Team")}
              value={progress?.steps?.find((s: any) => s.name === "team")?.done ? t("setup.invited", "Invited") : t("setup.pending", "Pending")}
            />
          </div>
        </section>

        <section className="space-y-6">
          <div className="rounded-[2rem] border border-[#13212c]/10 bg-white/85 p-6 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
                <Radar size={18} />
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                  {t("setup.howToUse", "How to use this wizard")}
                </p>
                <h2 className="mt-1 text-lg font-semibold text-[#13212c]">{t("setup.whatToDoFirst", "What to do first")}</h2>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              <GuidePanel
                title={t("setup.guide1Title", "Finish the warehouse shell first")}
                detail={t("setup.guide1Body", "Warehouse and location steps give later client, SKU, and picking data somewhere real to live.")}
              />
              <GuidePanel
                title={t("setup.guide2Title", "Use realistic defaults")}
                detail={t("setup.guide2Body", "This trial is most useful when you enter real naming, layout, and client information rather than placeholder values.")}
              />
              <GuidePanel
                title={t("setup.guide3Title", "Treat setup as the launch pad")}
                detail={t("setup.guide3Body", "Once this checklist is done, the guidance across dashboard, receiving, inventory, and shipping becomes actionable.")}
              />
            </div>
          </div>

          <div className="rounded-[2rem] border border-[#13212c]/10 bg-white/85 p-6 shadow-[0_24px_60px_rgba(19,33,44,0.08)]">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("setup.progress", "Progress snapshot")}</p>
            <h2 className="mt-2 text-lg font-semibold text-[#13212c]">{t("setup.progressTitle", "How complete is this workspace?")}</h2>
            <div className="mt-4 h-2 rounded-full bg-[#ece7dc]">
              <div className="h-2 rounded-full bg-[#13212c]" style={{ width: `${percent}%` }} />
            </div>
            <p className="mt-3 text-sm text-[#61717d]">
              {t("setup.progressBody", "{completed} of {total} setup checkpoints are already completed.", {
                completed: completedCount,
                total: totalCount,
              })}
            </p>
            <div className="mt-5 space-y-2 text-sm text-[#61717d]">
              <p>{t("setup.snapshotLocations", "Projected locations: {count}", { count: summary.locations })}</p>
              <p>{t("setup.snapshotSkus", "Draft SKUs entered: {count}", { count: summary.skuCount })}</p>
              <p>{t("setup.snapshotTeam", "Draft team members: {count}", { count: summary.teamCount })}</p>
            </div>
          </div>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("setup.steps", "Setup steps")}</p>
          <div className="mt-4 space-y-2">
            {steps.map((item, index) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setStep(index)}
                className={`w-full rounded-[1.2rem] border px-4 py-3 text-left transition ${
                  index === step
                    ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                    : "border-[#13212c]/8 bg-[#f7f4ee] text-[#13212c] hover:bg-white"
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-lg">{item.icon}</span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{item.title}</p>
                    <p className={`mt-1 text-xs leading-5 ${index === step ? "text-[#d1dde5]" : "text-[#677581]"}`}>
                      {item.description}
                    </p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="rounded-[1.9rem] border border-[#13212c]/10 bg-white/82 p-8 shadow-[0_20px_52px_rgba(19,33,44,0.06)]">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-[#13212c]/10 bg-[#f7f4ee] text-2xl">
              {currentStep.icon}
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                {t("setup.currentStep", "Current step")}
              </p>
              <h2 className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-[#13212c]">{currentStep.title}</h2>
            </div>
          </div>

          <p className="mt-4 max-w-2xl text-sm leading-7 text-[#61717d]">{currentStep.description}</p>

          <div className="mt-6">{currentStep.fields}</div>
        </section>
      </div>

      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <button
          onClick={() => setStep(Math.max(0, step - 1))}
          disabled={step === 0}
          className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 px-5 py-2.5 text-sm font-medium text-[#687783] transition hover:bg-white disabled:opacity-30"
        >
          <ChevronLeft size={16} />
          {t("setup.back", "Back")}
        </button>
        {step < steps.length - 1 ? (
          <button
            onClick={() => setStep(step + 1)}
            className="inline-flex items-center gap-2 rounded-full bg-[#13212c] px-6 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040]"
          >
            {t("common.next", "Next")}
            <ArrowRight size={16} />
          </button>
        ) : (
          <button
            onClick={handleFinish}
            disabled={quickSetup.isPending}
            className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-6 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-white transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {quickSetup.isPending ? t("setup.settingUp", "Setting up...") : t("setup.finish", "Finish setup")}
            <CheckCircle2 size={16} />
          </button>
        )}
      </div>

      <p className="text-center text-xs uppercase tracking-[0.18em] text-[#8a98a4]">
        {t("setup.footer", "You can skip steps and come back later from Settings.")}
      </p>
    </div>
  );
}

function WizardSignal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.3rem] border border-white/10 bg-white/5 p-4">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#96aab7]">{label}</p>
      <p className="mt-2 text-lg font-semibold text-[#f4efe8]">{value}</p>
    </div>
  );
}

function GuidePanel({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4">
      <p className="text-sm font-semibold text-[#13212c]">{title}</p>
      <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{detail}</p>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "password" | "select";
  options?: string[];
}) {
  if (type === "select") {
    return (
      <div>
        <label className="mb-1.5 block text-sm font-medium text-[#334351]">{label}</label>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
        >
          {options?.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-[#334351]">{label}</label>
      {type === "password" ? (
        <PasswordInput
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
        />
      )}
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-[#334351]">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        step={step}
        min={0}
        className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
      />
    </div>
  );
}

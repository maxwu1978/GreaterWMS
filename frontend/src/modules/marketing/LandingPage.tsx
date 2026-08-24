import { ArrowRight, Boxes, Bot, ChevronRight, ClipboardList, MapPinned, PackageCheck, Radar, ScanLine, ShieldCheck, Truck, Users, Workflow } from "lucide-react";
import { Link } from "react-router-dom";
import warehouseTeamScene from "../../assets/warehouse-team-scene.svg";
import { useI18n } from "../../shared/i18n";

export default function LandingPage() {
  const { t } = useI18n();
  const opsProof = [
    { label: t("landing.metricReceiving", "Receiving"), value: t("landing.metricReceivingValue", "12 bays"), accent: "bg-[#f7bf45]" },
    { label: t("landing.metricOrders", "Orders queued"), value: "184", accent: "bg-[#63e6be]" },
    { label: t("landing.metricAgv", "AGV-ready zones"), value: "08", accent: "bg-[#8db6ff]" },
  ];
  const shiftSignals = [
    { icon: ScanLine, label: t("landing.signalInbound", "Inbound scan accuracy"), value: "99.4%" },
    { icon: Truck, label: t("landing.signalCarrier", "Carrier-ready orders"), value: "146" },
    { icon: Bot, label: t("landing.signalAutomation", "Automation readiness"), value: t("landing.signalAutomationValue", "Mapped") },
  ];
  const workflow = [
    {
      label: t("landing.workflowReceiveLabel", "Receive"),
      title: t("landing.workflowReceiveTitle", "Confirm inbound work without losing variance."),
      detail: t(
        "landing.workflowReceiveDetail",
        "Scan arrivals, record differences, and create putaway work from the same flow.",
      ),
    },
    {
      label: t("landing.workflowPickLabel", "Pick"),
      title: t("landing.workflowPickTitle", "Keep outbound work tied to live inventory."),
      detail: t(
        "landing.workflowPickDetail",
        "Operators move from released orders to picking, shipping, returns, and billing context without switching tools.",
      ),
    },
    {
      label: t("landing.workflowAutomateLabel", "Automate"),
      title: t("landing.workflowAutomateTitle", "Protect today’s workflow as automation gets closer."),
      detail: t(
        "landing.workflowAutomateDetail",
        "Task queues, location coordinates, and API surfaces give AGV projects a clean handoff when the site is ready.",
      ),
    },
  ];
  const pillars = [
    {
      icon: Radar,
      eyebrow: t("landing.pillarAgvEyebrow", "AGV-ready core"),
      title: t("landing.pillarAgvTitle", "Built for the handoff from manual operations to automation."),
      body: t(
        "landing.pillarAgvBody",
        "WMS QuickStart keeps locations, tasks, and API surfaces structured so the warehouse does not have to replace the system later.",
      ),
    },
    {
      icon: MapPinned,
      eyebrow: t("landing.pillarRolloutEyebrow", "Practical rollout"),
      title: t("landing.pillarRolloutTitle", "Implementation support for warehouses that need real process help."),
      body: t(
        "landing.pillarRolloutBody",
        "The offer fits growing 3PL teams that want a faster go-live, cleaner warehouse habits, and a clear upgrade path.",
      ),
    },
    {
      icon: Workflow,
      eyebrow: t("landing.pillarCostEyebrow", "Lower total cost"),
      title: t("landing.pillarCostTitle", "A middle path between spreadsheet workarounds and enterprise WMS spend."),
      body: t(
        "landing.pillarCostBody",
        "Teams get stronger 3PL workflows and client visibility without taking on a long enterprise rollout before they are ready.",
      ),
    },
  ];
  const proof = [
    { label: t("landing.proofBillingLabel", "3PL billing"), value: t("landing.proofBillingValue", "Storage, handling, and service billing in one system") },
    { label: t("landing.proofFlowLabel", "Operator flow"), value: t("landing.proofFlowValue", "Receiving, putaway, inventory, pick, ship, return") },
    { label: t("landing.proofVisibilityLabel", "Client visibility"), value: t("landing.proofVisibilityValue", "Portal views for inventory, orders, and invoices") },
  ];
  const features = [
    {
      icon: ScanLine,
      title: t("landing.featureDailyTitle", "Run daily warehouse work in one place"),
      body: t(
        "landing.featureDailyBody",
        "Receiving, putaway, inventory checks, picking, shipping, and returns stay in one operating surface instead of scattered tools.",
      ),
    },
    {
      icon: ClipboardList,
      title: t("landing.featureBillingTitle", "Bill 3PL customers without spreadsheet cleanup"),
      body: t(
        "landing.featureBillingBody",
        "Storage, handling, and service activity can roll into billing logic without rebuilding the month-end process outside the system.",
      ),
    },
    {
      icon: Users,
      title: t("landing.featurePortalTitle", "Give customers their own visibility"),
      body: t(
        "landing.featurePortalBody",
        "Client portal views for inventory, orders, and invoices help reduce email-based status requests and manual reporting work.",
      ),
    },
    {
      icon: ShieldCheck,
      title: t("landing.featureAutomationTitle", "Start now without betting against future automation"),
      body: t(
        "landing.featureAutomationBody",
        "Location structure, task orchestration, and API-ready flows are designed so the WMS does not need to be replaced when AGV becomes real.",
      ),
    },
  ];
  const journey = [
    {
      step: "01",
      title: t("landing.journeyPlanTitle", "Choose a plan and create your workspace"),
      body: t(
        "landing.journeyPlanBody",
        "Start a 14-day trial, register your company, and create the operator account that will own the warehouse.",
      ),
    },
    {
      step: "02",
      title: t("landing.journeySetupTitle", "Load the basics and start running real work"),
      body: t(
        "landing.journeySetupBody",
        "Add locations, SKUs, and users, then begin receiving, inventory, and outbound flow from the same dashboard.",
      ),
    },
    {
      step: "03",
      title: t("landing.journeyEvaluateTitle", "Decide if the fit is right before rollout"),
      body: t(
        "landing.journeyEvaluateBody",
        "Use the trial to evaluate your operating rhythm, client visibility, and billing workflow before committing to a broader deployment.",
      ),
    },
  ];
  return (
    <div className="min-h-screen bg-[#f2efe8] text-[#13212c]">
      <header className="absolute inset-x-0 top-0 z-20">
        <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-4 md:flex-nowrap md:justify-between md:px-8 md:py-5">
          <Link to="/" className="flex min-w-0 items-center gap-2 sm:gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/40 bg-[#13212c] text-[#f6f2ea] sm:h-10 sm:w-10">
              <Boxes size={18} />
            </div>
            <div className="min-w-0">
              <p className="text-xs uppercase text-[#536272]">MaxSmart</p>
              <p className="truncate text-sm font-semibold text-[#13212c] sm:text-base">WMS QuickStart</p>
            </div>
          </Link>

          <nav className="hidden items-center gap-8 text-sm text-[#3e4f5f] md:flex">
            <a href="#why" className="transition-colors hover:text-[#13212c]">{t("landing.whyUs", "Why us")}</a>
            <a href="#features" className="transition-colors hover:text-[#13212c]">{t("landing.features", "Features")}</a>
            <a href="#trial" className="transition-colors hover:text-[#13212c]">{t("common.startTrial", "Start trial")}</a>
          </nav>

          <div className="ml-auto flex shrink-0 items-center justify-end gap-2 sm:gap-3">
            <Link
              to="/login"
              className="hidden rounded-full bg-[#13212c] px-3.5 py-2 text-sm font-semibold text-[#f8f4ec] transition hover:bg-[#1b2c39] sm:inline-flex sm:border sm:border-[#13212c]/15 sm:bg-transparent sm:px-4 sm:font-medium sm:text-[#13212c] sm:hover:border-[#13212c]/35 sm:hover:bg-transparent"
            >
              {t("common.signIn", "Sign in")}
            </Link>
            <Link
              to="/register"
              className="hidden rounded-full bg-[#13212c] px-4 py-2 text-sm font-medium text-[#f8f4ec] transition hover:bg-[#1b2c39] sm:inline-flex"
            >
              {t("common.startTrial", "Start trial")}
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="landing-grid relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(247,191,69,0.18),_transparent_30%),radial-gradient(circle_at_80%_25%,_rgba(20,39,55,0.14),_transparent_34%),linear-gradient(180deg,_rgba(255,255,255,0.24),_rgba(255,255,255,0))]" />
          <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-[#f2efe8] to-transparent" />

          <div className="relative mx-auto grid min-h-[100svh] max-w-7xl items-start px-4 pb-12 pt-28 md:px-8 lg:min-h-screen lg:grid-cols-[minmax(0,0.95fr)_minmax(320px,0.8fr)] lg:items-end lg:gap-10 lg:pb-20">
            <div className="min-w-0 max-w-2xl pb-8 lg:pb-0">
              <p className="animate-rise hidden break-words text-xs uppercase text-[#5f6d7c] sm:block">
                <span className="hidden sm:inline">{t("landing.heroEyebrow", "AGV-ready warehouse software for growing 3PL operators")}</span>
              </p>
              <h1 className="animate-rise-delayed mt-0 max-w-sm break-words text-[2.25rem] font-semibold leading-[0.96] text-[#13212c] sm:hidden">
                {t("common.signIn", "Sign in")}
              </h1>
              <h1 className="animate-rise-delayed mt-5 hidden max-w-4xl break-words font-semibold leading-[0.92] text-[#13212c] sm:block sm:text-[3.2rem] md:text-[4.8rem] lg:text-[6.2rem]">
                {t("landing.heroTitle", "The warehouse system that looks forward to automation.")}
              </h1>
              <p className="animate-rise-soft mt-6 hidden max-w-xl text-base leading-7 text-[#425261] sm:block md:text-lg">
                {t("landing.heroBody", "WMS QuickStart helps small and midsize 3PL warehouses run receiving, inventory, picking, shipping, returns, and client billing now, without choosing a dead-end system before AGV becomes realistic.")}
              </p>

              <div className="animate-rise-soft mt-5 grid gap-2 sm:hidden">
                <Link
                  to="/login"
                  className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.08em] text-[#f6f2ea] transition hover:bg-[#1d3140]"
                >
                  {t("common.signIn", "Sign in")}
                  <ArrowRight size={16} />
                </Link>
                <p className="text-center text-sm text-[#5b6a77]">
                  <Link to="/register" className="font-semibold text-[#13212c] underline-offset-4 hover:underline">
                    {t("common.startTrial", "Start trial")}
                  </Link>
                </p>
              </div>

              <div className="animate-rise-soft mt-6 hidden flex-wrap gap-3 text-xs uppercase text-[#5b6b79] sm:flex">
                <span className="rounded-full border border-[#13212c]/10 bg-white/50 px-3 py-2">{t("landing.badgeTrial", "14-day trial")}</span>
                <span className="rounded-full border border-[#13212c]/10 bg-white/50 px-3 py-2">{t("landing.badgeCard", "No credit card to start")}</span>
                <span className="rounded-full border border-[#13212c]/10 bg-white/50 px-3 py-2">{t("landing.badgeSetup", "Warehouse setup + operator login")}</span>
              </div>

              <div className="animate-rise-soft mt-8 hidden flex-col gap-3 sm:flex sm:flex-row">
                <Link
                  to="/register"
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-6 py-3.5 text-sm font-semibold uppercase text-[#f6f2ea] transition hover:bg-[#1d3140]"
                >
                  {t("common.startFreeTrial", "Start free trial")}
                  <ArrowRight size={16} />
                </Link>
                <a
                  href="#trial"
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-[#13212c]/15 px-6 py-3.5 text-sm font-semibold uppercase text-[#13212c] transition hover:border-[#13212c]/40"
                >
                  {t("landing.seeTrial", "See how trial works")}
                  <ChevronRight size={16} />
                </a>
              </div>

              <div className="mt-10 hidden gap-3 text-sm text-[#31414f] sm:grid sm:grid-cols-3">
                <QuickNote label={t("landing.startHere", "Start here")} value={t("landing.startHereBody", "Register your warehouse and admin account in a few minutes.")} />
                <QuickNote label={t("landing.duringTrial", "During trial")} value={t("landing.duringTrialBody", "Test receiving, picking, shipping, portal visibility, and billing flow.")} />
                <QuickNote label={t("landing.afterEvaluation", "After evaluation")} value={t("landing.afterEvaluationBody", "Keep using the same WMS as your operation grows toward automation.")} />
              </div>
            </div>

            <div className="relative mt-10 hidden min-w-0 lg:mt-0 lg:block">
              <div className="landing-orbit absolute inset-0 rounded-[2rem] bg-[radial-gradient(circle,_rgba(247,191,69,0.3),_transparent_62%)] blur-2xl" />
              <div className="relative overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[#10212d] p-5 text-[#f5efe6] shadow-[0_30px_80px_rgba(19,33,44,0.22)]">
                <div className="overflow-hidden rounded-[1.6rem] border border-white/10 bg-[#0c1922]">
                <img
                  src={warehouseTeamScene}
                  alt={t("landing.heroImageAlt", "Illustrated warehouse team coordinating receiving, inventory, and outbound work.")}
                  className="h-[280px] w-full object-cover"
                />
              </div>
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div>
                  <p className="text-xs uppercase text-[#9bb2c2]">{t("landing.opsDeck", "Operations deck")}</p>
                  <h2 className="mt-2 text-2xl font-semibold">{t("landing.liveBoard", "DFW 3PL live board")}</h2>
                </div>
                <div className="rounded-full border border-white/10 px-3 py-1 text-xs uppercase text-[#f7bf45]">
                  {t("landing.live", "live")}
                </div>
              </div>

              <div className="mt-5 space-y-5">
                <div className="rounded-[1.4rem] border border-white/10 bg-white/5 px-4 py-4 text-sm leading-6 text-[#d6e1e8]">
                  {t(
                    "landing.opsDeckBody",
                    "Shift leads can see inbound pressure, inventory control, outbound readiness, and automation signals in one operating picture."
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {opsProof.map((item) => (
                    <Metric key={item.label} label={item.label} value={item.value} accent={item.accent} />
                  ))}
                </div>

                  <div className="grid min-w-0 gap-4 md:grid-cols-[1.2fr_0.8fr]">
                    <div className="min-w-0 rounded-[1.5rem] border border-white/10 bg-white/5 p-4">
                      <div className="flex items-center justify-between text-sm text-[#a9bfcc]">
                        <span>{t("landing.motion", "Warehouse motion")}</span>
                        <span>{t("landing.today", "Today")}</span>
                      </div>
                      <div className="mt-4 grid grid-cols-4 gap-2">
                        {Array.from({ length: 12 }).map((_, index) => (
                          <div
                            key={index}
                            className="rounded-md bg-gradient-to-t from-[#f7bf45] to-[#ffdd8b]"
                            style={{ height: `${28 + ((index * 17) % 64)}px`, opacity: 0.55 + (index % 4) * 0.1 }}
                          />
                        ))}
                      </div>
                      <div className="mt-5 flex items-center gap-3 text-sm text-[#d4e2ea]">
                        <Radar size={16} className="text-[#f7bf45]" />
                        <span>{t("landing.motionBody", "Standardized locations and task flow stay compatible with future AGV routing.")}</span>
                      </div>
                    </div>

                    <div className="min-w-0 rounded-[1.5rem] border border-white/10 bg-[#0c1922] p-4">
                      <p className="text-sm text-[#a9bfcc]">{t("landing.shiftFocus", "Shift focus")}</p>
                      <div className="mt-4 space-y-4">
                        {shiftSignals.map((item) => (
                          <Signal key={item.label} icon={item.icon} label={item.label} value={item.value} />
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 border-t border-white/10 pt-4 text-sm text-[#d4e2ea] sm:grid-cols-3">
                    {proof.map((item) => (
                      <div key={item.label}>
                        <p className="text-xs uppercase text-[#8ea5b7]">{item.label}</p>
                        <p className="mt-2 leading-6">{item.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="why" className="border-t border-[#13212c]/10 bg-[#ede8dd]">
          <div className="mx-auto max-w-7xl px-5 py-20 md:px-8">
            <div className="grid gap-10 lg:grid-cols-[0.85fr_1.15fr]">
              <div className="min-w-0">
                <p className="break-words text-xs uppercase text-[#6d7a88]">
                  {t("landing.whyEyebrow", "Why teams switch")}
                </p>
                <h2 className="mt-4 max-w-md break-words text-4xl font-semibold text-[#13212c]">
                  {t(
                    "landing.whyTitle",
                    "A practical WMS for 3PL warehouses that have outgrown spreadsheets but are not ready for an enterprise rollout.",
                  )}
                </h2>
              </div>

              <div className="grid min-w-0 gap-10 md:grid-cols-3 md:gap-6">
                {pillars.map((pillar) => (
                  <div key={pillar.title} className="min-w-0 border-l border-[#13212c]/10 pl-5">
                    <pillar.icon className="text-[#13212c]" size={20} />
                    <p className="mt-5 break-words text-xs uppercase text-[#7a8896]">{pillar.eyebrow}</p>
                    <h3 className="mt-3 break-words text-xl font-semibold leading-8 text-[#13212c]">{pillar.title}</h3>
                    <p className="mt-4 break-words text-sm leading-7 text-[#495968]">{pillar.body}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="border-t border-[#13212c]/10 bg-[#f6f2ea]">
          <div className="mx-auto max-w-7xl px-5 py-20 md:px-8">
            <div className="grid gap-10 lg:grid-cols-[0.78fr_1.22fr]">
              <div className="min-w-0">
                <p className="break-words text-xs uppercase text-[#6d7a88]">
                  {t("landing.featuresEyebrow", "Operating coverage")}
                </p>
                <h2 className="mt-4 break-words text-4xl font-semibold text-[#13212c]">
                  {t(
                    "landing.featuresTitle",
                    "Run receiving, inventory, outbound, returns, portal visibility, and billing from one shared workspace.",
                  )}
                </h2>
                <p className="mt-5 max-w-md text-sm leading-7 text-[#495968]">
                  {t(
                    "landing.featuresBody",
                    "Warehouse, admin, and client-facing teams work from the same source of operational truth instead of stitching status together after the fact.",
                  )}
                </p>
              </div>

              <div className="grid min-w-0 gap-5 md:grid-cols-2">
                {features.map((feature) => (
                  <div
                    key={feature.title}
                    className="min-w-0 rounded-[1.6rem] border border-[#13212c]/10 bg-white/70 p-6 shadow-[0_15px_40px_rgba(19,33,44,0.05)]"
                  >
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#13212c] text-[#f6f2ea]">
                      <feature.icon size={18} />
                    </div>
                    <h3 className="mt-5 break-words text-xl font-semibold leading-8 text-[#13212c]">{feature.title}</h3>
                    <p className="mt-3 break-words text-sm leading-7 text-[#51616f]">{feature.body}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="flow" className="bg-[#13212c] text-[#f4efe8]">
          <div className="mx-auto max-w-7xl px-5 py-20 md:px-8">
            <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr]">
              <div className="min-w-0">
                <p className="break-words text-xs uppercase text-[#99adbd]">
                  {t("landing.workflowEyebrow", "Warehouse rhythm")}
                </p>
                <h2 className="mt-4 break-words text-4xl font-semibold">
                  {t("landing.workflowTitle", "One operating loop from dock arrival to customer billing.")}
                </h2>
                <p className="mt-5 max-w-md text-sm leading-7 text-[#b8cad6]">
                  {t(
                    "landing.workflowBody",
                    "Each step keeps inventory, task status, and client context connected so daily work does not drift into side spreadsheets.",
                  )}
                </p>
              </div>

              <div className="min-w-0 space-y-6">
                {workflow.map((item, index) => (
                  <div key={item.label} className="group relative min-w-0 border-t border-white/10 pt-6 first:border-t-0 first:pt-0">
                    <div className="flex min-w-0 items-start gap-4 sm:gap-5">
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/5 text-xs uppercase text-[#f7bf45]">
                        0{index + 1}
                      </div>
                      <div className="min-w-0">
                        <p className="break-words text-xs uppercase text-[#8fa7b6]">{item.label}</p>
                        <h3 className="mt-2 break-words text-2xl font-semibold">{item.title}</h3>
                        <p className="mt-3 max-w-2xl break-words text-sm leading-7 text-[#c7d6df]">{item.detail}</p>
                      </div>
                    </div>
                    <div className="pointer-events-none absolute left-6 top-12 h-full w-px bg-gradient-to-b from-[#f7bf45]/70 to-transparent group-last:hidden" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="trial" className="border-t border-[#13212c]/10 bg-[#e8dfd0]">
          <div className="mx-auto max-w-7xl px-5 py-20 md:px-8">
            <div className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr]">
              <div className="min-w-0">
                <p className="break-words text-xs uppercase text-[#6d7a88]">
                  {t("landing.trialEyebrow", "Trial path")}
                </p>
                <h2 className="mt-4 break-words text-4xl font-semibold text-[#13212c]">
                  {t("landing.trialTitle", "Start with a concrete 14-day evaluation.")}
                </h2>
                <p className="mt-5 max-w-md text-sm leading-7 text-[#495968]">
                  {t(
                    "landing.trialBody",
                    "Create the workspace, choose the plan, set up the basics, and test real receiving and outbound flow before expanding the rollout.",
                  )}
                </p>

                <div className="mt-8 rounded-[1.6rem] border border-[#13212c]/10 bg-[#13212c] p-6 text-[#f4efe8]">
                  <p className="text-xs uppercase text-[#f7bf45]">
                    {t("landing.trialPanelEyebrow", "Start free")}
                  </p>
                  <p className="mt-3 text-3xl font-semibold">
                    {t("landing.trialPanelTitle", "14-day trial for Starter and Growth plans")}
                  </p>
                  <p className="mt-4 text-sm leading-7 text-[#c5d4dc]">
                    {t(
                      "landing.trialPanelBody",
                      "No credit card to start. Register the company, choose the plan, and go directly into the app to set up locations, SKUs, users, and operating flow.",
                    )}
                  </p>
                  <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                    <Link
                      to="/register"
                      className="inline-flex items-center justify-center gap-2 rounded-full bg-[#f7bf45] px-5 py-3 text-sm font-semibold uppercase text-[#13212c] transition hover:bg-[#ffd26f]"
                    >
                      {t("landing.createTrialAccount", "Create trial account")}
                      <ArrowRight size={16} />
                    </Link>
                    <Link
                      to="/login"
                      className="inline-flex items-center justify-center gap-2 rounded-full border border-white/15 px-5 py-3 text-sm font-semibold uppercase text-[#f4efe8] transition hover:border-white/35"
                    >
                      {t("landing.alreadyRegistered", "Already registered")}
                    </Link>
                  </div>
                </div>
              </div>

              <div className="min-w-0 space-y-5">
                {journey.map((item) => (
                  <div
                    key={item.step}
                    className="min-w-0 rounded-[1.6rem] border border-[#13212c]/10 bg-white/65 p-6 shadow-[0_15px_35px_rgba(19,33,44,0.06)]"
                  >
                    <div className="flex min-w-0 items-start gap-4 sm:gap-5">
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-[#13212c]/10 bg-[#13212c] text-xs font-semibold uppercase text-[#f7bf45]">
                        {item.step}
                      </div>
                      <div className="min-w-0">
                        <h3 className="break-words text-2xl font-semibold leading-8 text-[#13212c]">{item.title}</h3>
                        <p className="mt-3 break-words text-sm leading-7 text-[#4f5f6c]">{item.body}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="cta" className="border-t border-[#13212c]/10 bg-[#f6f2ea]">
          <div className="mx-auto flex max-w-7xl flex-col gap-8 px-5 py-16 md:px-8 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="break-words text-xs uppercase text-[#6d7a88]">
                {t("landing.ctaEyebrow", "Ready to evaluate")}
              </p>
              <h2 className="mt-4 max-w-2xl break-words text-4xl font-semibold text-[#13212c]">
                {t("landing.ctaTitle", "Create the trial workspace and see whether the system fits your warehouse flow.")}
              </h2>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Link
                to="/register"
                className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-6 py-3.5 text-sm font-semibold uppercase text-[#f6f2ea] transition hover:bg-[#1f3443]"
              >
                {t("common.startTrial", "Start trial")}
                <PackageCheck size={16} />
              </Link>
              <Link
                to="/login"
                className="inline-flex items-center justify-center gap-2 rounded-full border border-[#13212c]/15 px-6 py-3.5 text-sm font-semibold uppercase text-[#13212c] transition hover:border-[#13212c]/35"
              >
                {t("landing.operatorSignIn", "Operator sign in")}
              </Link>
            </div>
          </div>
        </section>
      </main>

    </div>
  );
}

function QuickNote({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.3rem] border border-[#13212c]/10 bg-white/60 p-4">
      <p className="break-words text-[11px] uppercase text-[#72808d]">{label}</p>
      <p className="mt-2 text-sm leading-6 text-[#334351]">{value}</p>
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="rounded-[1.2rem] border border-white/10 bg-white/5 p-4">
      <div className={`h-1.5 w-12 rounded-full ${accent}`} />
      <p className="mt-4 break-words text-xs uppercase text-[#90a6b5]">{label}</p>
      <p className="mt-2 text-3xl font-semibold">{value}</p>
    </div>
  );
}

function Signal({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof ScanLine;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-start justify-between gap-3 border-b border-white/10 pb-3 last:border-b-0 last:pb-0 sm:items-center sm:gap-4">
      <div className="flex min-w-0 items-center gap-3">
        <div className="shrink-0 rounded-full border border-white/10 bg-white/5 p-2">
          <Icon size={15} />
        </div>
        <span className="min-w-0 break-words text-sm text-[#bdd0db]">{label}</span>
      </div>
      <span className="shrink-0 text-sm font-semibold text-white">{value}</span>
    </div>
  );
}

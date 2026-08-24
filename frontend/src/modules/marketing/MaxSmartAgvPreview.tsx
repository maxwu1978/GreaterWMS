import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  Boxes,
  Check,
  ChevronDown,
  Factory,
  Menu,
  Ruler,
  ShieldCheck,
  Truck,
  Warehouse,
  Workflow,
  X,
} from "lucide-react";

const siteRoot = "https://maxsmartagv.ai";
const heroImage = `${siteRoot}/images/generated/vestwoods-hero-canva-final-web.jpg`;

const paths = [
  {
    number: "01",
    icon: Warehouse,
    label: "WMS QuickStart",
    title: "Stabilize warehouse operations.",
    body: "Start with inventory, barcode discipline, receiving, putaway and outbound flow before a larger automation program.",
    cta: "Start WMS QuickStart",
    href: `${siteRoot}/services/wms-quickstart/`,
  },
  {
    number: "02",
    icon: Ruler,
    label: "AGV readiness",
    title: "Check your AGV readiness.",
    body: "Map routes, handoff points and system boundaries before committing to a vehicle, pilot or control layer.",
    cta: "Check AGV readiness",
    href: `${siteRoot}/services/agv-wms-readiness-diagnostic/`,
  },
  {
    number: "03",
    icon: Workflow,
    label: "WMS / WCS integration",
    title: "Connect WMS, WCS and fleet operations.",
    body: "Use a system-first path when dispatch logic, status feedback and brownfield integration are the real bottlenecks.",
    cta: "Plan the control layer",
    href: `${siteRoot}/services/erp-wms-wcs-integration/`,
  },
];

const decisionPaths = [
  {
    id: "warehouse",
    label: "Warehouse",
    title: "Start with a stable WMS foundation.",
    body: "For inventory accuracy, receiving, putaway and pallet flow, establish the operating baseline before adding vehicles.",
    cta: "Start WMS QuickStart",
    href: `${siteRoot}/services/wms-quickstart/`,
  },
  {
    id: "manufacturing",
    label: "Manufacturing",
    title: "Map line-side flow before adding automation.",
    body: "For parts-to-line delivery, connect warehouse, buffer and production handoffs before choosing the fleet.",
    cta: "Explore manufacturing automation",
    href: `${siteRoot}/solutions/manufacturing-automation/`,
  },
  {
    id: "3pl",
    label: "3PL",
    title: "Build visibility that can scale across clients.",
    body: "For changing customer profiles, stabilize inventory and define the control layer before expanding to AGV execution.",
    cta: "Check AGV readiness",
    href: `${siteRoot}/services/agv-wms-readiness-diagnostic/`,
  },
];

const solutions = [
  {
    icon: Warehouse,
    label: "Warehouse",
    title: "Stable pallet flow",
    body: "Replenishment, putaway and internal transport for sites where aisle width, timing and repeatability matter.",
    href: `${siteRoot}/solutions/warehouse-automation/`,
  },
  {
    icon: Factory,
    label: "Manufacturing",
    title: "Keep production moving",
    body: "Connect warehouse, buffer and production nodes with clear handoffs and a phased automation path.",
    href: `${siteRoot}/solutions/manufacturing-automation/`,
  },
  {
    icon: Truck,
    label: "3PL",
    title: "A clearer base for 3PL teams",
    body: "Give growing 3PL teams better inventory control now and a practical route toward WMS, WCS and AGV later.",
    href: `${siteRoot}/solutions/3pl-warehouse-automation/`,
  },
];

const products = [
  {
    image: `${siteRoot}/images/products/ptjs/BT-F15P-KL.png`,
    label: "Pallet AGV",
    title: "Pallet transport AGV",
    bestFor: "Pallet transport, replenishment and putaway",
    spec: "1.5t class · 2D / 3D laser navigation",
    href: `${siteRoot}/products/pallet-agv/`,
  },
  {
    image: `${siteRoot}/images/products/ztd/BN-F12ESL-ZL.png`,
    label: "Narrow-aisle AGV",
    title: "High-reach stacker AGV",
    bestFor: "High-bay storage and narrow aisles",
    spec: "1.2t · up to 8.5m lift · dense storage",
    href: `${siteRoot}/products/narrow-aisle-agv/`,
  },
  {
    image: `${siteRoot}/images/products/ptjs/BT-D10SF-ZL.png`,
    label: "Forklift AGV",
    title: "Autonomous forklift AGV",
    bestFor: "Automated pallet pickup and transport",
    spec: "Fork pickup · repeatable pallet handling",
    href: `${siteRoot}/products/forklift-agv/`,
  },
];

const cases = [
  {
    label: "Warehouse case",
    title: "High-bay and narrow-aisle automation",
    body: "A scenario-led path for stable pallet handoff, replenishment and retrieval in constrained storage.",
    href: `${siteRoot}/case-studies/warehouse-high-bay/`,
  },
  {
    label: "Manufacturing case",
    title: "Line-side delivery",
    body: "A repeatable material flow between warehouse, buffer and production without forcing a single-step cutover.",
    href: `${siteRoot}/case-studies/manufacturing-logistics/`,
  },
  {
    label: "System case",
    title: "VMI warehouse coordination",
    body: "A broader control-layer story for supplier planning, dispatch visibility and WMS/TMS-linked execution.",
    href: `${siteRoot}/case-studies/vmi-manufacturing-logistics/`,
  },
];

const deploymentSteps = [
  {
    number: "01",
    title: "Review the site",
    body: "Confirm routes, handoffs, payloads and operating constraints.",
  },
  {
    number: "02",
    title: "Map the workflow",
    body: "Define the WMS, WCS and fleet responsibilities before a pilot.",
  },
  {
    number: "03",
    title: "Run a focused pilot",
    body: "Measure one repeatable workflow with a clear success target.",
  },
  {
    number: "04",
    title: "Scale with control",
    body: "Expand the fleet and integration layer when the process is ready.",
  },
];

export default function MaxSmartAgvPreview() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [selectedDecision, setSelectedDecision] = useState("warehouse");
  const activeDecision = decisionPaths.find((path) => path.id === selectedDecision) ?? decisionPaths[0];

  useEffect(() => {
    const previousTitle = document.title;
    const previousLanguage = document.documentElement.lang;
    document.title = "Start with the right workflow | MaxSmart AGV";
    document.documentElement.lang = "en";
    return () => {
      document.title = previousTitle;
      document.documentElement.lang = previousLanguage;
    };
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
  }

  function closeMenu() {
    setMenuOpen(false);
  }

  return (
    <div className="min-h-screen bg-[#f4f5f7] text-[#15263d]">
      <header className="sticky top-0 z-50 border-b border-[#d9dee5] bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-[72px] max-w-[1440px] items-center justify-between px-5 lg:px-10">
          <a href="#top" className="flex items-center gap-3" onClick={closeMenu}>
            <span className="flex h-10 w-10 items-center justify-center bg-[#ffcd00] text-[#15263d]">
              <Boxes size={22} strokeWidth={2.5} />
            </span>
            <span className="leading-none">
              <span className="block text-[15px] font-bold tracking-[0.14em] text-[#15263d]">MAXSMART</span>
              <span className="mt-1 block text-[10px] font-semibold uppercase tracking-[0.2em] text-[#6c7887]">Warehouse automation</span>
            </span>
          </a>

          <nav className="hidden items-center gap-8 text-[13px] font-semibold uppercase tracking-[0.08em] text-[#46566a] lg:flex">
            <a className="transition-colors hover:text-[#15263d]" href="#paths">Start here</a>
            <a className="transition-colors hover:text-[#15263d]" href="#solutions">Solutions</a>
            <a className="transition-colors hover:text-[#15263d]" href="#products">Products</a>
            <a className="transition-colors hover:text-[#15263d]" href="#cases">Cases</a>
          </nav>

          <div className="hidden items-center gap-5 lg:flex">
            <span className="text-xs font-semibold text-[#6c7887]">North America · GreenEcoPower Corp</span>
            <a className="inline-flex items-center gap-2 bg-[#ffcd00] px-4 py-3 text-xs font-bold uppercase tracking-[0.08em] text-[#15263d] transition-colors hover:bg-[#f0bd00]" href="#contact">
              Contact the team
              <ArrowRight size={15} />
            </a>
          </div>

          <button
            type="button"
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            className="inline-flex h-11 w-11 items-center justify-center border border-[#d9dee5] text-[#15263d] lg:hidden"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        {menuOpen && (
          <nav className="border-t border-[#d9dee5] bg-white px-5 py-4 lg:hidden">
            <div className="mx-auto grid max-w-[1440px] gap-1 text-sm font-semibold text-[#15263d]">
              {[
                ["Start here", "#paths"],
                ["Solutions", "#solutions"],
                ["Products", "#products"],
                ["Cases", "#cases"],
                ["Contact the team", "#contact"],
              ].map(([label, href]) => (
                <a key={href} className="border-b border-[#edf0f3] py-3" href={href} onClick={closeMenu}>
                  {label}
                </a>
              ))}
            </div>
          </nav>
        )}
      </header>

      <main id="top">
        <section data-testid="agv-preview-hero" className="relative isolate min-h-[650px] overflow-hidden bg-[#0b1e39] text-white lg:min-h-[600px]">
          <img className="absolute inset-0 h-full w-full object-cover object-center opacity-80" src={heroImage} alt="Automated warehouse vehicle moving through a logistics workflow" />
          <div className="absolute inset-0 bg-[#0b1e39]/60" />
          <div className="relative mx-auto grid min-h-[650px] max-w-[1440px] items-center gap-10 px-5 py-8 lg:min-h-[600px] lg:grid-cols-[1.08fr_0.92fr] lg:px-10 lg:py-8">
            <div className="max-w-3xl">
              <p className="mb-5 inline-flex items-center gap-3 text-xs font-bold uppercase tracking-[0.18em] text-[#ffcd00]">
                <span className="h-px w-10 bg-[#ffcd00]" />
                North America operations
              </p>
              <h1 className="max-w-3xl text-[clamp(2.6rem,5vw,4.8rem)] font-semibold leading-[0.98] tracking-[-0.03em]">
                Start with the right workflow.
              </h1>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-[#e3e9f0] lg:text-xl">
                Start with WMS QuickStart, assess AGV fit, or plan the WMS/WCS layer you'll need as you scale. We help warehouse, 3PL, e-commerce and light manufacturing teams move in phases.
              </p>
              <div className="mt-7 flex flex-col gap-3 sm:flex-row">
                <a className="inline-flex items-center justify-center gap-3 bg-[#ffcd00] px-6 py-4 text-sm font-bold uppercase tracking-[0.06em] text-[#15263d] transition-colors hover:bg-[#f0bd00]" href={`${siteRoot}/services/wms-quickstart/`}>
                  Start WMS QuickStart
                  <ArrowRight size={17} />
                </a>
                <a className="inline-flex items-center justify-center gap-3 border border-white/60 px-6 py-4 text-sm font-bold uppercase tracking-[0.06em] text-white transition-colors hover:border-[#ffcd00] hover:text-[#ffcd00]" href={`${siteRoot}/services/agv-wms-readiness-diagnostic/`}>
                  Check AGV readiness
                </a>
              </div>
              <div className="mt-7 grid max-w-2xl grid-cols-3 border-y border-white/20 py-3 text-sm">
                <div className="border-r border-white/20 pr-4">
                  <p className="text-xl font-semibold text-[#ffcd00]">01</p>
                  <p className="mt-1 text-xs leading-5 text-[#d4dce6]">One stable workflow</p>
                </div>
                <div className="border-r border-white/20 px-4">
                  <p className="text-xl font-semibold text-[#ffcd00]">02</p>
                  <p className="mt-1 text-xs leading-5 text-[#d4dce6]">A clear WMS-to-AGV path</p>
                </div>
                <div className="pl-4">
                  <p className="text-xl font-semibold text-[#ffcd00]">03</p>
                  <p className="mt-1 text-xs leading-5 text-[#d4dce6]">A phased rollout</p>
                </div>
              </div>
            </div>

            <div className="hidden border-l-4 border-[#ffcd00] bg-[#102949]/90 p-7 lg:ml-auto lg:block lg:max-w-md">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#ffcd00]">Choose a first step</p>
              <h2 className="mt-4 text-3xl font-semibold leading-tight">Choose the control layer first.</h2>
              <p className="mt-5 text-base leading-7 text-[#d4dfe9]">Begin with the workflow, the system boundary and the rollout risk. Then choose the smallest scope that proves value.</p>
              <a className="mt-7 inline-flex items-center gap-2 text-sm font-bold text-white underline decoration-[#ffcd00] decoration-2 underline-offset-8 hover:text-[#ffcd00]" href={`${siteRoot}/insights/when-you-need-wcs-vs-wms-for-agv/`}>
                Compare WMS, WCS and AGV roles
                <ArrowRight size={16} />
              </a>
            </div>
          </div>
        </section>

        <section id="paths" className="bg-white">
          <div className="mx-auto max-w-[1440px] px-5 py-20 lg:px-10 lg:py-28">
            <div className="max-w-3xl">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#7b8795]">Start here</p>
              <h2 className="mt-4 text-4xl font-semibold leading-tight tracking-[-0.02em] text-[#15263d] lg:text-5xl">Start with the real bottleneck.</h2>
              <p className="mt-5 max-w-2xl text-lg leading-8 text-[#526174]">Start with a scope you can approve, measure and expand.</p>
            </div>
            <div className="mt-12 grid gap-px border border-[#d9dee5] bg-[#d9dee5] lg:grid-cols-3">
              {paths.map((path) => (
                <a key={path.number} className="group bg-white p-7 transition-colors hover:bg-[#f4f7fa] lg:p-9" href={path.href}>
                  <div className="flex items-center justify-between">
                    <path.icon size={25} strokeWidth={1.6} className="text-[#15263d]" />
                    <span className="text-xs font-bold tracking-[0.12em] text-[#8b96a4]">{path.number}</span>
                  </div>
                  <p className="mt-12 text-xs font-bold uppercase tracking-[0.15em] text-[#7b8795]">{path.label}</p>
                  <h3 className="mt-4 text-2xl font-semibold leading-tight text-[#15263d]">{path.title}</h3>
                  <p className="mt-4 text-base leading-7 text-[#526174]">{path.body}</p>
                  <span className="mt-8 inline-flex items-center gap-2 text-sm font-bold text-[#15263d] group-hover:text-[#7e6200]">
                    {path.cta}
                    <ArrowRight size={16} />
                  </span>
                </a>
              ))}
            </div>
          </div>
        </section>

        <section id="guide" className="bg-[#0b1e39] text-white">
          <div className="mx-auto max-w-[1440px] px-5 py-20 lg:px-10 lg:py-24">
            <div className="grid gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:gap-20">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#ffcd00]">Find your first move</p>
                <h2 className="mt-4 text-4xl font-semibold leading-tight tracking-[-0.02em] lg:text-5xl">Not sure where to start?</h2>
                <p className="mt-5 max-w-xl text-lg leading-8 text-[#d4dfe9]">Choose the operating context first. We will point you toward the smallest scope that can prove value.</p>
                <div className="mt-8 grid gap-2 sm:grid-cols-3" role="tablist" aria-label="Choose an operating context">
                  {decisionPaths.map((path) => {
                    const isSelected = path.id === selectedDecision;
                    return (
                      <button
                        key={path.id}
                        type="button"
                        role="tab"
                        id={`decision-tab-${path.id}`}
                        aria-selected={isSelected}
                        aria-controls="decision-panel"
                        className={`border px-4 py-3 text-left text-sm font-bold transition-colors ${isSelected ? "border-[#ffcd00] bg-[#ffcd00] text-[#15263d]" : "border-white/30 text-white hover:border-[#ffcd00] hover:text-[#ffcd00]"}`}
                        onClick={() => setSelectedDecision(path.id)}
                      >
                        {path.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div id="decision-panel" role="tabpanel" aria-labelledby={`decision-tab-${activeDecision.id}`} className="border-l-4 border-[#ffcd00] pl-7 lg:pl-9">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#ffcd00]">Recommended first step</p>
                <h3 className="mt-4 max-w-xl text-3xl font-semibold leading-tight lg:text-4xl">{activeDecision.title}</h3>
                <p className="mt-5 max-w-xl text-base leading-7 text-[#d4dfe9]">{activeDecision.body}</p>
                <a className="mt-7 inline-flex items-center gap-2 text-sm font-bold text-white underline decoration-[#ffcd00] decoration-2 underline-offset-8 hover:text-[#ffcd00]" href={activeDecision.href}>
                  {activeDecision.cta}
                  <ArrowRight size={16} />
                </a>
              </div>
            </div>
          </div>
        </section>

        <section id="solutions" className="border-y border-[#d9dee5] bg-[#f4f5f7]">
          <div className="mx-auto max-w-[1440px] px-5 py-20 lg:px-10 lg:py-28">
            <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-20">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#7b8795]">Industries</p>
                <h2 className="mt-4 text-4xl font-semibold leading-tight tracking-[-0.02em] text-[#15263d]">Choose the workflow first.</h2>
                <a className="mt-8 inline-flex items-center gap-2 text-sm font-bold text-[#15263d] underline decoration-[#ffcd00] decoration-2 underline-offset-8" href={`${siteRoot}/solutions/warehouse-automation/`}>
                  Explore solutions
                  <ArrowRight size={16} />
                </a>
              </div>
              <div className="grid gap-8 md:grid-cols-3">
                {solutions.map((solution) => (
                  <a key={solution.label} className="group border-t-4 border-[#15263d] pt-5" href={solution.href}>
                    <solution.icon size={24} className="text-[#15263d]" strokeWidth={1.6} />
                    <p className="mt-7 text-xs font-bold uppercase tracking-[0.15em] text-[#7b8795]">{solution.label}</p>
                    <h3 className="mt-3 text-xl font-semibold leading-tight text-[#15263d]">{solution.title}</h3>
                    <p className="mt-3 text-sm leading-6 text-[#526174]">{solution.body}</p>
                    <span className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-[#15263d] group-hover:text-[#7e6200]">Explore <ArrowRight size={15} /></span>
                  </a>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="agv-amr" className="bg-white">
          <div className="mx-auto grid max-w-[1440px] gap-12 px-5 py-20 lg:grid-cols-[0.85fr_1.15fr] lg:items-center lg:px-10 lg:py-24">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#7b8795]">AGV or AMR?</p>
              <h2 className="mt-4 text-4xl font-semibold leading-tight tracking-[-0.02em] text-[#15263d] lg:text-5xl">Choose the approach that fits the floor.</h2>
              <p className="mt-5 max-w-xl text-lg leading-8 text-[#526174]">The right choice depends on route repeatability, payload, people flow and the systems already running at your site.</p>
            </div>
            <div className="grid gap-px border border-[#d9dee5] bg-[#d9dee5] md:grid-cols-2">
              <div className="bg-[#f4f5f7] p-7 lg:p-9">
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-[#7b8795]">AGV</p>
                <h3 className="mt-4 text-2xl font-semibold text-[#15263d]">Predictable movement</h3>
                <p className="mt-4 text-base leading-7 text-[#526174]">A strong fit for repeatable routes, defined handoffs and stable material flows.</p>
              </div>
              <div className="bg-white p-7 lg:p-9">
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-[#7b8795]">AMR</p>
                <h3 className="mt-4 text-2xl font-semibold text-[#15263d]">Flexible movement</h3>
                <p className="mt-4 text-base leading-7 text-[#526174]">A strong fit for changing environments, dynamic routes and flexible task assignment.</p>
              </div>
            </div>
          </div>
        </section>

        <section id="products" className="bg-white">
          <div className="mx-auto max-w-[1440px] px-5 py-20 lg:px-10 lg:py-28">
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
              <div className="max-w-3xl">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#7b8795]">Product families</p>
                <h2 className="mt-4 text-4xl font-semibold leading-tight tracking-[-0.02em] text-[#15263d] lg:text-5xl">Choose the right vehicle.</h2>
              </div>
              <a className="inline-flex items-center gap-2 text-sm font-bold text-[#15263d] underline decoration-[#ffcd00] decoration-2 underline-offset-8" href={`${siteRoot}/#products`}>
                View all products
                <ArrowRight size={16} />
              </a>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-3">
              {products.map((product) => (
                <a key={product.label} className="group border border-[#d9dee5] bg-white transition-shadow hover:shadow-[0_18px_36px_rgba(21,38,61,0.12)]" href={product.href}>
                  <div className="flex h-64 items-center justify-center bg-[#eef2f5] p-8">
                    <img className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-105" src={product.image} alt={product.title} loading="lazy" />
                  </div>
                  <div className="p-6">
                    <p className="text-xs font-bold uppercase tracking-[0.15em] text-[#7b8795]">{product.label}</p>
                    <h3 className="mt-3 text-2xl font-semibold text-[#15263d]">{product.title}</h3>
                    <p className="mt-3 text-sm leading-6 text-[#526174]"><span className="font-semibold text-[#15263d]">Best for:</span> {product.bestFor}</p>
                    <p className="mt-3 text-sm leading-6 text-[#526174]"><span className="font-semibold text-[#15263d]">Key spec:</span> {product.spec}</p>
                    <span className="mt-7 inline-flex items-center gap-2 text-sm font-bold text-[#15263d] group-hover:text-[#7e6200]">View category <ArrowRight size={15} /></span>
                  </div>
                </a>
              ))}
            </div>
          </div>
        </section>

        <section id="deployment" className="border-y border-[#d9dee5] bg-[#f4f5f7]">
          <div className="mx-auto max-w-[1440px] px-5 py-20 lg:px-10 lg:py-24">
            <div className="max-w-3xl">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#7b8795]">Deployment path</p>
              <h2 className="mt-4 text-4xl font-semibold leading-tight tracking-[-0.02em] text-[#15263d] lg:text-5xl">Plan the rollout before the fleet.</h2>
              <p className="mt-5 max-w-2xl text-lg leading-8 text-[#526174]">A phased rollout keeps the first project measurable and gives the next step a clear operating case.</p>
            </div>
            <div className="mt-12 grid gap-8 md:grid-cols-2 lg:grid-cols-4">
              {deploymentSteps.map((step) => (
                <div key={step.number} className="border-t-4 border-[#15263d] pt-5">
                  <p className="text-3xl font-light text-[#7e6200]">{step.number}</p>
                  <h3 className="mt-5 text-xl font-semibold text-[#15263d]">{step.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-[#526174]">{step.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="cases" className="bg-[#15263d] text-white">
          <div className="mx-auto max-w-[1440px] px-5 py-20 lg:px-10 lg:py-28">
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
              <div className="max-w-3xl">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#ffcd00]">Case studies</p>
                <h2 className="mt-4 text-4xl font-semibold leading-tight tracking-[-0.02em] lg:text-5xl">See the workflow first.</h2>
              </div>
              <a className="inline-flex items-center gap-2 text-sm font-bold text-white underline decoration-[#ffcd00] decoration-2 underline-offset-8" href={`${siteRoot}/case-studies/`}>
                View all cases
                <ArrowRight size={16} />
              </a>
            </div>
            <div className="mt-12 grid gap-8 lg:grid-cols-3">
              {cases.map((item, index) => (
                <a key={item.label} className="group border-t border-white/30 pt-6" href={item.href}>
                  <span className="text-4xl font-light text-[#ffcd00]">0{index + 1}</span>
                  <p className="mt-10 text-xs font-bold uppercase tracking-[0.15em] text-[#b8c3d0]">{item.label}</p>
                  <h3 className="mt-4 text-2xl font-semibold leading-tight">{item.title}</h3>
                  <p className="mt-4 text-base leading-7 text-[#d0d8e2]">{item.body}</p>
                  <span className="mt-7 inline-flex items-center gap-2 text-sm font-bold text-white group-hover:text-[#ffcd00]">Read case study <ArrowRight size={15} /></span>
                </a>
              ))}
            </div>
          </div>
        </section>

        <section id="contact" className="bg-white">
          <div className="mx-auto grid max-w-[1440px] gap-12 px-5 py-20 lg:grid-cols-[0.9fr_1.1fr] lg:px-10 lg:py-28">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#7b8795]">Next step</p>
              <h2 className="mt-4 max-w-xl text-4xl font-semibold leading-tight tracking-[-0.02em] text-[#15263d] lg:text-5xl">Make a clear first decision.</h2>
              <p className="mt-6 max-w-xl text-lg leading-8 text-[#526174]">Share the operating context, the main workflow and the scope you are considering. We can help decide whether to start with WMS, AGV readiness or a broader control layer.</p>
              <div className="mt-9 grid gap-4 text-sm text-[#526174] sm:grid-cols-2">
                {[
                  "One clear first scope",
                  "Phased rollout logic",
                  "Clear system boundaries",
                  "A quote based on real scope",
                ].map((item) => (
                  <div key={item} className="flex items-center gap-3 border-t border-[#d9dee5] pt-4">
                    <Check size={17} className="text-[#7e6200]" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>

            <form className="border border-[#d9dee5] bg-[#f4f5f7] p-6 md:p-8" onSubmit={handleSubmit}>
              <div className="flex items-start justify-between gap-6 border-b border-[#d9dee5] pb-5">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.15em] text-[#7b8795]">Project review</p>
                  <h3 className="mt-2 text-2xl font-semibold text-[#15263d]">Where is the decision stuck?</h3>
                </div>
                <ShieldCheck className="shrink-0 text-[#15263d]" size={24} strokeWidth={1.6} />
              </div>
              <div className="mt-7 grid gap-5 md:grid-cols-2">
                <label className="text-sm font-semibold text-[#15263d]">
                  Name
                  <input className="mt-2 w-full border border-[#c8d0da] bg-white px-4 py-3 font-normal outline-none transition-colors focus:border-[#15263d]" name="name" required />
                </label>
                <label className="text-sm font-semibold text-[#15263d]">
                  Company
                  <input className="mt-2 w-full border border-[#c8d0da] bg-white px-4 py-3 font-normal outline-none transition-colors focus:border-[#15263d]" name="company" required />
                </label>
                <label className="text-sm font-semibold text-[#15263d]">
                  Work email
                  <input className="mt-2 w-full border border-[#c8d0da] bg-white px-4 py-3 font-normal outline-none transition-colors focus:border-[#15263d]" name="email" type="email" required />
                </label>
                <label className="text-sm font-semibold text-[#15263d]">
                  First step
                  <span className="relative mt-2 block">
                    <select className="w-full appearance-none border border-[#c8d0da] bg-white px-4 py-3 font-normal outline-none transition-colors focus:border-[#15263d]" name="path" defaultValue="readiness">
                      <option value="wms">WMS QuickStart</option>
                      <option value="readiness">AGV readiness</option>
                      <option value="integration">WMS / WCS integration</option>
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#526174]" size={17} />
                  </span>
                </label>
                <label className="text-sm font-semibold text-[#15263d] md:col-span-2">
                  Main workflow or constraint
                  <textarea className="mt-2 min-h-28 w-full resize-y border border-[#c8d0da] bg-white px-4 py-3 font-normal outline-none transition-colors focus:border-[#15263d]" name="message" placeholder="For example: narrow aisle replenishment, line-side delivery, or ERP / WCS handoff" required />
                </label>
              </div>
              <div className="mt-7 flex flex-col gap-4 border-t border-[#d9dee5] pt-5 sm:flex-row sm:items-center sm:justify-between">
                {submitted ? <p data-testid="agv-preview-form-success" className="text-sm font-semibold text-[#3f6b4d]">Thanks. The local preview captured the form state.</p> : <p className="text-xs leading-5 text-[#7b8795]">The production form should connect to the inquiry endpoint before publishing.</p>}
                <button className="inline-flex items-center justify-center gap-2 bg-[#15263d] px-5 py-3 text-sm font-bold uppercase tracking-[0.06em] text-white transition-colors hover:bg-[#223c5f]" type="submit">
                  Request a project review
                  <ArrowRight size={16} />
                </button>
              </div>
            </form>
          </div>
        </section>
      </main>

      <footer className="border-t border-[#d9dee5] bg-[#f4f5f7]">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-5 py-7 text-xs text-[#6c7887] sm:flex-row sm:items-center sm:justify-between lg:px-10">
          <p>MaxSmart AGV · North America warehouse automation preview</p>
          <div className="flex gap-5">
            <a className="hover:text-[#15263d]" href={`${siteRoot}/services/wms-quickstart/`}>WMS QuickStart</a>
            <a className="hover:text-[#15263d]" href={`${siteRoot}/services/agv-wms-readiness-diagnostic/`}>AGV readiness</a>
            <a className="hover:text-[#15263d]" href="#contact">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
}

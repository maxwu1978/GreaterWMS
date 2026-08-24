import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Boxes, Check, ChevronLeft, ClipboardList, ScanLine, Users } from "lucide-react";
import { useAuthStore } from "../../shared/hooks/useAuth";
import { fetchSubscriptionPlans, registerTenant } from "../../shared/api/subscriptions";
import { queryKeys } from "../../shared/api/queryKeys";
import { getApiErrorMessage } from "../../shared/api/error-message";
import warehouseTeamScene from "../../assets/warehouse-team-scene.svg";
import { useI18n } from "../../shared/i18n";
import LegalDisclosure from "../../shared/components/LegalDisclosure";
import PasswordInput from "../../shared/components/PasswordInput";

interface Plan {
  code: string;
  name: string;
  price_monthly: number;
  max_clients: number;
  max_skus: number;
  max_users: number;
  trial_days: number;
}

export default function RegisterPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();

  const [step, setStep] = useState<"plan" | "info">("plan");
  const [selectedPlan, setSelectedPlan] = useState("starter");
  const [form, setForm] = useState({
    company_name: "",
    company_code: "",
    admin_name: "",
    admin_email: "",
    admin_password: "",
    confirm_password: "",
  });
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [acceptRiskNotice, setAcceptRiskNotice] = useState(false);

  const { data: plans = [] } = useQuery<Plan[]>({
    queryKey: queryKeys.subscriptions.plans(),
    queryFn: fetchSubscriptionPlans,
  });

  const selectedPlanDetails = plans.find((plan) => plan.code === selectedPlan);
  const onboardingNotes = [
    {
      icon: ScanLine,
      title: t("register.note1Title", "Start with the flow you already know"),
      body: t(
        "register.note1Body",
        "Use the trial to test receiving, inventory, picking, shipping, and returns without waiting for a large implementation.",
      ),
    },
    {
      icon: ClipboardList,
      title: t("register.note2Title", "Evaluate the whole 3PL operating rhythm"),
      body: t(
        "register.note2Body",
        "The point of the trial is not just login access. It is to see whether the product handles client visibility and billing with less manual cleanup.",
      ),
    },
    {
      icon: Users,
      title: t("register.note3Title", "Create the workspace your team will keep using"),
      body: t(
        "register.note3Body",
        "Register the company once, onboard the admin account, and keep the same structure as the warehouse grows toward automation.",
      ),
    },
  ];
  const trialTermsSections = [
    {
      title: t("legal.trialScopeTitle", "Trial scope"),
      body: t(
        "legal.trialScopeBody",
        "This trial is provided so your team can evaluate receiving, inventory, fulfillment, client portal, billing, and planning workflows in a live-like operating environment.",
      ),
    },
    {
      title: t("legal.noAdviceTitle", "No legal, tax, or regulatory advice"),
      body: t(
        "legal.noAdviceBody",
        "The product helps operate a warehouse. It does not replace legal review, tax advice, customs guidance, safety certification, or any regulatory sign-off required in your jurisdiction.",
      ),
    },
    {
      title: t("legal.availabilityTitle", "Evaluation environment"),
      body: t(
        "legal.availabilityBody",
        "The trial is offered for evaluation. Features, limits, and data handling processes may evolve as the product matures, and the customer should not treat the trial as a guaranteed production SLA.",
      ),
    },
  ];
  const dataResponsibilitySections = [
    {
      title: t("legal.permissionTitle", "Permission to upload data"),
      body: t(
        "legal.permissionBody",
        "You should only enter customer, inventory, billing, or warehouse data that you are authorized to upload, migrate, or process on behalf of your company or your clients.",
      ),
    },
    {
      title: t("legal.accuracyTitle", "Accuracy remains your responsibility"),
      body: t(
        "legal.accuracyBody",
        "The system can help structure operational data, but the legality, correctness, and contractual appropriateness of that data remain the customer’s responsibility.",
      ),
    },
    {
      title: t("legal.aiAssistTitle", "AI-assisted migration is reviewed, not automatic"),
      body: t(
        "legal.aiAssistBody",
        "If mapping or migration assistance is used, it should be treated as a draft recommendation. Final review and approval of imported warehouse and client data still belongs to the customer.",
      ),
    },
  ];

  const getPlanName = (plan?: Plan | null) => {
    if (!plan) {
      return t("register.plan.starter", "Starter");
    }
    return t(`register.plan.${plan.code}`, plan.name);
  };

  const updateName = (name: string) => {
    const code = name
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "")
      .slice(0, 10);
    setForm({ ...form, company_name: name, company_code: code });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccessMessage("");

    if (form.admin_password !== form.confirm_password) {
      setError(t("auth.passwordMismatch", "Passwords do not match"));
      return;
    }
    if (form.admin_password.length < 6) {
      setError(t("auth.passwordShort", "Password must be at least 6 characters"));
      return;
    }

    setLoading(true);
    try {
      const data = await registerTenant({
        company_name: form.company_name,
        company_code: form.company_code,
        admin_name: form.admin_name,
        admin_email: form.admin_email,
        admin_password: form.admin_password,
        plan_code: selectedPlan,
        accept_terms: acceptTerms,
        accept_risk_notice: acceptRiskNotice,
      });

      if (data.pending_approval) {
        setSuccessMessage(
          data.message ||
            t(
              "register.pendingApprovalBody",
              "Registration received. A platform administrator will review your workspace; you can sign in once it is approved.",
            ),
        );
        return;
      }

      if (data.verification_required) {
        setSuccessMessage(
          data.message ||
            t(
              "register.verificationEmailSentBody",
              "Verification email sent. Please verify your email before signing in.",
            ),
        );
        return;
      }

      setAuth(data.access_token, "tenant_admin", data.tenant_id, t("users.roleTenantAdmin", "Tenant Admin"), [
        "inbound_orders.manage",
        "inbound_orders.import",
        "receiving.execute",
        "outbound_orders.manage",
        "picking.execute",
        "shipping.execute",
        "master_data.manage",
        "users.manage",
        "billing.manage",
        "planner.manage",
      ]);
      navigate("/dashboard");
    } catch (err: any) {
      setError(getApiErrorMessage(err, "Registration failed. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f2efe8] text-[#13212c]">
      <div className="grid min-h-screen lg:grid-cols-[minmax(0,0.92fr)_minmax(420px,0.88fr)]">
        <section className="relative hidden overflow-hidden border-r border-[#13212c]/8 bg-[#13212c] px-10 py-10 text-[#f4efe8] lg:flex lg:flex-col">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(247,191,69,0.2),_transparent_28%),radial-gradient(circle_at_75%_18%,_rgba(141,182,255,0.16),_transparent_30%)]" />
          <div className="relative flex items-center justify-between">
            <Link to="/" className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-full border border-white/15 bg-white/5">
                <Boxes size={18} />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-[#9db1bf]">MaxSmart</p>
                <p className="font-semibold">WMS QuickStart</p>
              </div>
            </Link>
            <span className="rounded-full border border-white/10 px-3 py-1 text-xs uppercase tracking-[0.2em] text-[#f7bf45]">
              {t("auth.freeTrial", "free trial")}
            </span>
          </div>

          <div className="relative mt-auto max-w-xl pb-10 pt-16">
            <p className="text-xs uppercase tracking-[0.35em] text-[#9db1bf]">
              {t("register.startWorkspaceEyebrow", "Start the workspace")}
            </p>
            <h1 className="mt-5 text-5xl font-semibold tracking-[-0.04em]">
              {t("auth.registerHeroTitle", "Trial the product the same way a real warehouse team would use it.")}
            </h1>
            <p className="mt-6 max-w-lg text-base leading-8 text-[#c4d2db]">
              {t(
                "register.heroBody",
                "Choose the plan, create the company workspace, and move directly into real warehouse flow instead of testing disconnected demo screens.",
              )}
            </p>

            <div className="mt-8 overflow-hidden rounded-[1.8rem] border border-white/10 bg-[#0d1922] image-glow">
              <img
                src={warehouseTeamScene}
                alt={t(
                  "register.heroImageAlt",
                  "Warehouse team planning inbound, inventory, and outbound work during a trial evaluation.",
                )}
                className="h-[240px] w-full object-cover"
              />
            </div>

            <div className="mt-5 rounded-[1.5rem] border border-white/10 bg-white/5 px-5 py-4">
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#9fb2be]">
                {t("register.proofTitle", "What the trial should prove")}
              </p>
              <div className="mt-3 grid gap-3 text-sm leading-6 text-[#d4dfe6] sm:grid-cols-3">
                <p>{t("register.proof1", "Can your team receive and locate stock cleanly from day one?")}</p>
                <p>{t("register.proof2", "Can customer visibility and billing stay tied to warehouse truth?")}</p>
                <p>{t("register.proof3", "Can the system scale without a future rip-and-replace?")}</p>
              </div>
            </div>

            <div className="mt-8 grid gap-4">
              {onboardingNotes.map((item) => (
                <div key={item.title} className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                  <item.icon size={18} className="text-[#f7bf45]" />
                  <h3 className="mt-4 text-lg font-semibold">{item.title}</h3>
                  <p className="mt-2 text-sm leading-7 text-[#d2dee6]">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="flex items-center justify-center px-5 py-10 md:px-8">
          <div className="w-full max-w-2xl">
            <div className="mb-6 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Link to="/" className="text-xs uppercase tracking-[0.28em] text-[#7a8894]">
                  {t("common.backToSite", "Back to site")}
                </Link>
              </div>
              <p className="text-xs uppercase tracking-[0.22em] text-[#7a8894]">
                {step === "plan" ? t("auth.step1", "Step 1 of 2") : t("auth.step2", "Step 2 of 2")}
              </p>
            </div>

            <div className="mb-8 flex items-center gap-3">
              <ProgressPill active={step === "plan"} done={step === "info"} label={t("common.choosePlan", "Choose plan")} />
              <div className="h-px flex-1 bg-[#13212c]/10" />
              <ProgressPill active={step === "info"} done={false} label={t("common.createWorkspace", "Create workspace")} />
            </div>

            {step === "plan" && (
              <div className="space-y-5">
                <div>
                  <h1 className="text-4xl font-semibold tracking-[-0.03em] text-[#13212c]">
                    {t("auth.registerTitle", "Pick the trial that fits your warehouse.")}
                  </h1>
                  <p className="mt-4 max-w-xl text-sm leading-7 text-[#586773]">
                    {t("auth.registerBody", "Start with a plan, keep the trial concrete, and then decide whether the system fits your inventory, order volume, and client reporting needs.")}
                  </p>
                </div>

                <div className="grid gap-4">
                  {plans.map((plan) => {
                    const selected = selectedPlan === plan.code;
                    return (
                      <button
                        key={plan.code}
                        type="button"
                        onClick={() => setSelectedPlan(plan.code)}
                        className={`w-full rounded-[1.8rem] border p-6 text-left transition ${
                          selected
                            ? "border-[#13212c] bg-[#13212c] text-[#f4efe8] shadow-[0_20px_50px_rgba(19,33,44,0.18)]"
                            : "border-[#13212c]/10 bg-white/70 text-[#13212c] hover:border-[#13212c]/25"
                        }`}
                      >
                        <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
                          <div>
                            <div className="flex items-center gap-3">
                              <h3 className="text-2xl font-semibold">{getPlanName(plan)}</h3>
                              {plan.code === "growth" && (
                                <span className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${
                                  selected ? "bg-[#f7bf45] text-[#13212c]" : "bg-[#13212c]/6 text-[#13212c]"
                                }`}>
                                  {t("register.planPopular", "Popular")}
                                </span>
                              )}
                            </div>
                            <p className={`mt-3 text-sm leading-7 ${selected ? "text-[#d5e0e7]" : "text-[#5c6b77]"}`}>
                              {t("register.planLimits", "{clients} clients · {skus} SKUs · {users} users")
                                .replace("{clients}", formatLimit(plan.max_clients, t))
                                .replace("{skus}", formatLimit(plan.max_skus, t))
                                .replace("{users}", formatLimit(plan.max_users, t))}
                            </p>
                          </div>
                          <div className="text-left md:text-right">
                            <p className="text-4xl font-semibold tracking-[-0.03em]">${plan.price_monthly}</p>
                            <p className={`mt-1 text-xs uppercase tracking-[0.18em] ${selected ? "text-[#a8bcc8]" : "text-[#7a8894]"}`}>
                              {t("register.perMonth", "per month")}
                            </p>
                          </div>
                        </div>

                        <div className={`mt-5 flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.18em] ${selected ? "text-[#f7bf45]" : "text-[#6d7a88]"}`}>
                          <span>{t("register.planTrial", "{days}-day trial").replace("{days}", String(plan.trial_days))}</span>
                          <span>{t("register.noCreditCard", "No credit card")}</span>
                          <span>{t("register.upgradeAnytime", "Upgrade anytime")}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>

                <div className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/65 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-[#72808d]">
                    {t("register.selectedPath", "Selected path")}
                  </p>
                  <p className="mt-2 text-lg font-semibold text-[#13212c]">
                    {t("register.selectedPlanSummary", "{plan} plan with a {days}-day trial")
                      .replace("{plan}", getPlanName(selectedPlanDetails))
                      .replace("{days}", String(selectedPlanDetails?.trial_days || 14))}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#586773]">
                    {t(
                      "register.selectedPathBody",
                      "You will create the company account next and go directly into the app after registration.",
                    )}
                  </p>
                </div>

                <div className="flex flex-col gap-3 sm:flex-row">
                  <button
                    type="button"
                    onClick={() => setStep("info")}
                    className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-6 py-3.5 text-sm font-semibold uppercase tracking-[0.14em] text-[#f6f2ea] transition hover:bg-[#1c2f3d]"
                  >
                    {t("register.continueWorkspaceSetup", "Continue to workspace setup")}
                    <ArrowRight size={16} />
                  </button>
                  <Link
                    to="/login"
                    className="inline-flex items-center justify-center rounded-full border border-[#13212c]/12 px-6 py-3.5 text-sm font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:border-[#13212c]/28"
                  >
                    {t("register.alreadyRegistered", "Already registered")}
                  </Link>
                </div>
              </div>
            )}

            {step === "info" && (
              <div className="rounded-[2rem] border border-[#13212c]/10 bg-white/75 p-8 shadow-[0_28px_60px_rgba(19,33,44,0.08)] backdrop-blur">
                <button
                  type="button"
                  onClick={() => setStep("plan")}
                  className="inline-flex items-center gap-2 text-sm font-medium text-[#6b7884] transition hover:text-[#13212c]"
                >
                  <ChevronLeft size={16} />
                  {t("register.backToPlanSelection", "Back to plan selection")}
                </button>

                <div className="mt-6 rounded-[1.4rem] border border-[#13212c]/10 bg-[#f6f2ea] p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-[#72808d]">
                    {t("register.trialSummary", "Trial summary")}
                  </p>
                  <p className="mt-2 text-xl font-semibold text-[#13212c]">
                    {t("register.trialSummaryLine", "{plan} plan · {days}-day trial")
                      .replace("{plan}", getPlanName(selectedPlanDetails))
                      .replace("{days}", String(selectedPlanDetails?.trial_days || 14))}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#586773]">
                    {t(
                      "register.trialSummaryBody",
                      "Create the company workspace, onboard the admin account, and start testing daily warehouse flow right away.",
                    )}
                  </p>
                </div>

                <form onSubmit={handleSubmit} className="mt-8 space-y-5">
                  <div className="grid gap-4 md:grid-cols-2">
                    <Field label={t("register.companyName", "Company Name *")}>
                      <input
                        type="text"
                        value={form.company_name}
                        onChange={(e) => updateName(e.target.value)}
                        required
                        className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                        placeholder={t("register.companyNamePlaceholder", "Acme Logistics")}
                      />
                    </Field>
                    <Field
                      label={t("register.companyCode", "Company Code *")}
                      hint={t("register.companyCodeHint", "Unique short identifier")}
                    >
                      <input
                        type="text"
                        value={form.company_code}
                        onChange={(e) => setForm({ ...form, company_code: e.target.value.toUpperCase() })}
                        required
                        maxLength={10}
                        className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 font-mono outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                        placeholder={t("register.companyCodePlaceholder", "ACME")}
                      />
                    </Field>
                  </div>

                  <Field label={t("register.fullName", "Your Full Name *")}>
                    <input
                      type="text"
                      value={form.admin_name}
                      onChange={(e) => setForm({ ...form, admin_name: e.target.value })}
                      required
                      className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                      placeholder={t("register.fullNamePlaceholder", "John Smith")}
                    />
                  </Field>

                  <Field label={t("register.emailLabel", "Email *")}>
                    <input
                      type="email"
                      value={form.admin_email}
                      onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
                      required
                      className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                      placeholder={t("register.emailPlaceholder", "john@acmelogistics.com")}
                    />
                  </Field>

                  <div className="grid gap-4 md:grid-cols-2">
                    <Field label={t("register.passwordLabel", "Password *")}>
                      <PasswordInput
                        value={form.admin_password}
                        onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
                        required
                        minLength={6}
                        className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                      />
                    </Field>
                    <Field label={t("register.confirmPasswordLabel", "Confirm Password *")}>
                      <PasswordInput
                        value={form.confirm_password}
                        onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
                        required
                        className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                      />
                    </Field>
                  </div>

                  {error && (
                    <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
                  )}

                  {successMessage && (
                    <div className="rounded-[1.6rem] border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-900">
                      <p className="font-semibold uppercase tracking-[0.16em] text-emerald-700">
                        {t("register.checkEmail", "Check your email")}
                      </p>
                      <p className="mt-2 leading-6">{successMessage}</p>
                      <div className="mt-4 flex flex-wrap gap-3">
                        <Link
                          to="/login"
                          className="inline-flex items-center justify-center rounded-full bg-[#13212c] px-5 py-2.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#f6f2ea]"
                        >
                          {t("register.goToSignIn", "Go to sign in")}
                        </Link>
                        <button
                          type="button"
                          onClick={() => setSuccessMessage("")}
                          className="inline-flex items-center justify-center rounded-full border border-[#13212c]/12 px-5 py-2.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                        >
                          {t("register.editDetails", "Edit details")}
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-[#f7f4ee] px-5 py-4 text-sm text-[#586773]">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#7a8894]">
                      {t("register.trialNotices", "Trial notices")}
                    </p>
                    <div className="mt-3 space-y-3">
                      <label className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={acceptTerms}
                          onChange={(e) => setAcceptTerms(e.target.checked)}
                          className="mt-1 h-4 w-4 accent-[#13212c]"
                        />
                        <span>
                          {t(
                            "register.noticeTerms",
                            "I agree to the trial terms and understand this product is an operational software evaluation, not legal, tax, or regulatory advice.",
                          )}
                        </span>
                      </label>
                      <label className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={acceptRiskNotice}
                          onChange={(e) => setAcceptRiskNotice(e.target.checked)}
                          className="mt-1 h-4 w-4 accent-[#13212c]"
                        />
                        <span>
                          {t(
                            "register.noticeRisk",
                            "I confirm I have permission to enter customer, inventory, and billing data, and I remain responsible for the legality and accuracy of that data.",
                          )}
                        </span>
                      </label>
                    </div>
                    <div className="mt-4 space-y-3">
                      <LegalDisclosure
                        title={t("legal.viewTrialTerms", "View trial terms")}
                        summary={t("legal.readBeforeAccepting", "Read before accepting")}
                        sections={trialTermsSections}
                      />
                      <LegalDisclosure
                        title={t("legal.viewDataResponsibility", "View data responsibility notice")}
                        summary={t("legal.readBeforeUploading", "Read before uploading customer data")}
                        sections={dataResponsibilitySections}
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={loading || Boolean(successMessage) || !acceptTerms || !acceptRiskNotice}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3.5 text-sm font-semibold uppercase tracking-[0.14em] text-[#f6f2ea] transition hover:bg-[#1c2f3d] disabled:opacity-50"
                  >
                    {loading
                      ? t("register.creatingWarehouse", "Creating your warehouse...")
                      : successMessage
                        ? t("register.verificationSent", "Verification email sent")
                        : t("register.createTrialAccount", "Create trial account")}
                    <ArrowRight size={16} />
                  </button>

                  <p className="text-center text-xs uppercase tracking-[0.16em] text-[#8a98a4]">
                    {t(
                      "register.trialAcceptanceNote",
                      "Trial access requires acceptance of the operational and data responsibility notices above",
                    )}
                  </p>
                </form>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function ProgressPill({ active, done, label }: { active: boolean; done: boolean; label: string }) {
  return (
    <div className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm ${
      done
        ? "bg-[#13212c] text-[#f6f2ea]"
        : active
          ? "border border-[#13212c]/15 bg-white/75 text-[#13212c]"
          : "border border-[#13212c]/10 bg-white/45 text-[#86939e]"
    }`}>
      <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
        done ? "bg-[#f7bf45] text-[#13212c]" : active ? "bg-[#13212c] text-[#f6f2ea]" : "bg-[#d6ddd8] text-[#67747f]"
      }`}>
        {done ? <Check size={14} /> : label.charAt(0)}
      </span>
      <span className="font-medium">{label}</span>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="block">
      <span className="mb-1.5 block text-sm font-medium text-[#334351]">{label}</span>
      {children}
      {hint ? <span className="mt-1.5 block text-xs text-[#7a8894]">{hint}</span> : null}
    </div>
  );
}

function formatLimit(value: number, t: (key: string, fallback: string) => string) {
  return value === 999999 ? t("common.unlimited", "Unlimited") : value.toLocaleString();
}

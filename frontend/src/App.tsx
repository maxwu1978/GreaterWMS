import { Suspense, lazy, type ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { defaultRouteForRole, useAuthStore } from "./shared/hooks/useAuth";
import Layout from "./shared/components/Layout";
const LandingPage = lazy(() => import("./modules/marketing/LandingPage"));
const MaxSmartAgvPreview = lazy(() => import("./modules/marketing/MaxSmartAgvPreview"));
const LoginPage = lazy(() => import("./modules/auth/LoginPage"));
const RegisterPage = lazy(() => import("./modules/auth/RegisterPage"));
const ForgotPasswordPage = lazy(() => import("./modules/auth/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("./modules/auth/ResetPasswordPage"));
const DashboardPage = lazy(() => import("./modules/dashboard/DashboardPage"));
const ReceivingPage = lazy(() => import("./modules/receiving/ReceivingPage"));
const InboundOrderDetailPage = lazy(() => import("./modules/receiving/InboundOrderDetailPage"));
const InventoryPage = lazy(() => import("./modules/inventory/InventoryPage"));
const PutawayPage = lazy(() => import("./modules/putaway/PutawayPage"));
const PickingPage = lazy(() => import("./modules/picking/PickingPage"));
const ShippingPage = lazy(() => import("./modules/shipping/ShippingPage"));
const BillingPage = lazy(() => import("./modules/billing/BillingPage"));
const ClientProfilesPage = lazy(() => import("./modules/billing/BillingSettingsPage"));
const ReceivingCodeSettingsPage = lazy(() => import("./modules/receiving/ReceivingCodeSettingsPage"));
const ReceivingLabelSettingsPage = lazy(() => import("./modules/receiving/ReceivingLabelSettingsPage"));
const AgvPage = lazy(() => import("./modules/agv/AgvPage"));
const PricingPage = lazy(() => import("./modules/admin/PricingPage"));
const SetupWizardPage = lazy(() => import("./modules/admin/SetupWizardPage"));
const SubscriptionPage = lazy(() => import("./modules/admin/SubscriptionPage"));
const DataMigrationPage = lazy(() => import("./modules/admin/DataMigrationPage"));
const UsersPage = lazy(() => import("./modules/admin/UsersPage"));
const PlatformWorkspacesPage = lazy(() => import("./modules/admin/PlatformWorkspacesPage"));
const WarehousePlannerPage = lazy(() => import("./modules/admin/WarehousePlannerPage"));
const WarehousesPage = lazy(() => import("./modules/admin/WarehousesPage"));
const SkusPage = lazy(() => import("./modules/admin/SkusPage"));
const AgentConsolePage = lazy(() => import("./modules/admin/AgentConsolePage"));
const AgentSettingsPage = lazy(() => import("./modules/admin/AgentSettingsPage"));
const PortalDashboard = lazy(() => import("./modules/client-portal/PortalDashboard"));
const PortalInventory = lazy(() => import("./modules/client-portal/PortalInventory"));
const PortalOrders = lazy(() => import("./modules/client-portal/PortalOrders"));
const PortalInvoices = lazy(() => import("./modules/client-portal/PortalInvoices"));

function PageFallback() {
  return (
    <div className="min-h-[40vh] px-6 py-16">
      <div className="mx-auto max-w-3xl rounded-[1.5rem] border border-[#13212c]/8 bg-white/85 px-6 py-10 text-center shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
        <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">Loading</p>
        <p className="mt-3 text-lg font-semibold text-[#13212c]">Preparing the next workspace</p>
        <p className="mt-2 text-sm leading-6 text-[#61717d]">We are loading the page and its operational context.</p>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function TenantRoute({ children }: { children: ReactNode }) {
  const role = useAuthStore((s) => s.role);
  if (role === "platform_admin") return <Navigate to="/users" replace />;
  return <>{children}</>;
}

function PlatformRoute({ children }: { children: ReactNode }) {
  const role = useAuthStore((s) => s.role);
  if (role !== "platform_admin") return <Navigate to={defaultRouteForRole(role)} replace />;
  return <>{children}</>;
}

export default function App() {
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const defaultRoute = defaultRouteForRole(role);
  const isNativeShell = window.location.protocol === "capacitor:";

  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={token ? <Navigate to={defaultRoute} replace /> : isNativeShell ? <LoginPage /> : <LandingPage />} />
        <Route path="/agv-site-preview" element={<MaxSmartAgvPreview />} />
        <Route path="/login" element={token ? <Navigate to={defaultRoute} replace /> : <LoginPage />} />
        <Route path="/register" element={token ? <Navigate to={defaultRoute} replace /> : <RegisterPage />} />
        <Route path="/forgot-password" element={token ? <Navigate to={defaultRoute} replace /> : <ForgotPasswordPage />} />
        <Route path="/reset-password" element={token ? <Navigate to={defaultRoute} replace /> : <ResetPasswordPage />} />

        {/* Authenticated app routes */}
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<TenantRoute><DashboardPage /></TenantRoute>} />
          <Route path="/receiving" element={<TenantRoute><ReceivingPage /></TenantRoute>} />
          <Route path="/receiving/orders/:orderId" element={<TenantRoute><InboundOrderDetailPage /></TenantRoute>} />
          <Route path="/putaway" element={<TenantRoute><PutawayPage /></TenantRoute>} />
          <Route path="/inventory" element={<TenantRoute><InventoryPage /></TenantRoute>} />
          <Route path="/picking" element={<TenantRoute><PickingPage /></TenantRoute>} />
          <Route path="/shipping" element={<TenantRoute><ShippingPage /></TenantRoute>} />
          <Route path="/billing" element={<TenantRoute><BillingPage /></TenantRoute>} />
          <Route path="/billing-settings" element={<TenantRoute><Navigate to="/clients" replace /></TenantRoute>} />
          <Route path="/receiving-code-settings" element={<TenantRoute><ReceivingCodeSettingsPage /></TenantRoute>} />
          <Route path="/receiving-label-settings" element={<TenantRoute><ReceivingLabelSettingsPage /></TenantRoute>} />
          <Route path="/warehouses" element={<TenantRoute><WarehousesPage /></TenantRoute>} />
          <Route path="/clients" element={<TenantRoute><ClientProfilesPage /></TenantRoute>} />
          <Route path="/skus" element={<TenantRoute><SkusPage /></TenantRoute>} />
          <Route path="/agv" element={<TenantRoute><AgvPage /></TenantRoute>} />

          {/* Subscription management */}
          <Route path="/pricing" element={<TenantRoute><PricingPage /></TenantRoute>} />
          <Route path="/subscription" element={<TenantRoute><SubscriptionPage /></TenantRoute>} />
          <Route path="/migration" element={<TenantRoute><DataMigrationPage /></TenantRoute>} />
          <Route path="/agent-console" element={<TenantRoute><AgentConsolePage /></TenantRoute>} />
          <Route path="/agent-settings" element={<TenantRoute><AgentSettingsPage /></TenantRoute>} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/workspaces" element={<PlatformRoute><PlatformWorkspacesPage /></PlatformRoute>} />
          <Route path="/warehouse-planner" element={<TenantRoute><WarehousePlannerPage /></TenantRoute>} />
          <Route path="/setup" element={<TenantRoute><SetupWizardPage /></TenantRoute>} />

          {/* Client portal routes */}
          <Route path="/portal/dashboard" element={<TenantRoute><PortalDashboard /></TenantRoute>} />
          <Route path="/portal/inventory" element={<TenantRoute><PortalInventory /></TenantRoute>} />
          <Route path="/portal/orders" element={<TenantRoute><PortalOrders /></TenantRoute>} />
          <Route path="/portal/invoices" element={<TenantRoute><PortalInvoices /></TenantRoute>} />
        </Route>

        <Route path="*" element={<Navigate to={token ? defaultRoute : "/"} replace />} />
      </Routes>
    </Suspense>
  );
}

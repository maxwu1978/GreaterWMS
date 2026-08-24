/**
 * Main application layout — sidebar navigation + content area.
 * Responsive: sidebar collapses to bottom bar on mobile.
 */

import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { defaultRouteForRole, useAuthStore } from "../hooks/useAuth";
import PaywallBanner from "./PaywallBanner";
import {
  LayoutDashboard,
  PackageOpen,
  Warehouse,
  ClipboardList,
  Boxes,
  Truck,
  Receipt,
  Users,
  Bot,
  LogOut,
  Menu,
  X,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  CornerUpLeft,
  Database,
  UserCog,
  Map,
  Tags,
  Building2,
} from "lucide-react";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { useI18n } from "../i18n";
import OfflineOutboxBanner from "./OfflineOutboxBanner";

export default function Layout() {
  const { role, permissions, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { t } = useI18n();
  const homePath = defaultRouteForRole(role);
  const backHomeLabel =
    role === "platform_admin"
      ? t("common.backToUsers", "Back to users")
      : t("common.backToDashboard", "Back to dashboard");

  const operatorNav = [
    { to: "/dashboard", icon: LayoutDashboard, label: t("nav.dashboard", "Dashboard") },
    { to: "/receiving", icon: PackageOpen, label: t("nav.receiving", "Receiving") },
    { to: "/putaway", icon: Boxes, label: t("nav.putaway", "Putaway") },
    { to: "/inventory", icon: Warehouse, label: t("nav.inventory", "Inventory") },
    { to: "/picking", icon: ClipboardList, label: t("nav.picking", "Picking") },
    { to: "/shipping", icon: Truck, label: t("nav.shipping", "Shipping") },
    { to: "/billing", icon: Receipt, label: t("nav.billing", "Billing") },
    { to: "/clients", icon: Users, label: t("nav.clients", "Clients") },
    { to: "/receiving-code-settings", icon: Tags, label: t("nav.receivingCodeSettings", "Receiving Code Settings") },
    { to: "/receiving-label-settings", icon: Tags, label: t("nav.receivingLabelSettings", "Receiving Label Settings") },
    { to: "/warehouses", icon: Warehouse, label: t("nav.warehouses", "Warehouses") },
    { to: "/skus", icon: PackageOpen, label: t("nav.skus", "SKUs") },
    { to: "/users", icon: UserCog, label: t("nav.users", "Users") },
    { to: "/warehouse-planner", icon: Map, label: t("nav.warehousePlanner", "Warehouse Planner") },
    { to: "/migration", icon: Database, label: t("nav.migration", "Migration") },
    { to: "/agent-console", icon: Bot, label: t("nav.agentConsole", "Agent Console") },
    { to: "/agent-settings", icon: Bot, label: t("nav.agentSettings", "Agent Settings") },
    { to: "/agv", icon: Bot, label: t("nav.agv", "AGV") },
  ];

  const platformNav = [
    { to: "/users", icon: UserCog, label: t("nav.users", "Users") },
    { to: "/workspaces", icon: Building2, label: t("nav.workspaces", "Workspaces") },
  ];

  const operatorNavGroups = [
    {
      id: "operations",
      label: t("section.operations", "Operations"),
      items: operatorNav.filter((item) =>
        ["/dashboard", "/receiving", "/putaway", "/inventory", "/picking", "/shipping", "/billing"].includes(item.to)
      ),
    },
    {
      id: "masterData",
      label: t("section.masterData", "Master Data"),
      items: operatorNav.filter((item) => ["/clients", "/receiving-code-settings", "/receiving-label-settings", "/warehouses", "/skus", "/users"].includes(item.to)),
    },
    {
      id: "planning",
      label: t("section.planningImport", "Planning & Import"),
      items: operatorNav.filter((item) => ["/warehouse-planner", "/migration"].includes(item.to)),
    },
    {
      id: "automation",
      label: t("section.automation", "Automation"),
      items: operatorNav.filter((item) => ["/agent-console", "/agent-settings", "/agv"].includes(item.to)),
    },
  ];

  const clientNav = [
    { to: "/portal/dashboard", icon: LayoutDashboard, label: t("nav.dashboard", "Dashboard") },
    { to: "/portal/inventory", icon: Warehouse, label: t("nav.inventory", "Inventory") },
    { to: "/portal/orders", icon: ClipboardList, label: t("nav.orders", "Orders") },
    { to: "/portal/invoices", icon: Receipt, label: t("nav.invoices", "Invoices") },
  ];

  const platformNavGroups = [
    {
      id: "platform",
      label: t("section.platformAdmin", "Platform Admin"),
      items: platformNav,
    },
  ];

  const routeMeta = {
    "/dashboard": { section: t("section.operations", "Operations"), title: t("nav.dashboard", "Dashboard"), previous: null, next: "/receiving" },
    "/receiving": { section: t("section.operations", "Operations"), title: t("nav.receiving", "Receiving"), previous: "/dashboard", next: "/putaway" },
    "/putaway": { section: t("section.operations", "Operations"), title: t("nav.putaway", "Putaway"), previous: "/receiving", next: "/inventory" },
    "/inventory": { section: t("section.operations", "Operations"), title: t("nav.inventory", "Inventory"), previous: "/putaway", next: "/picking" },
    "/picking": { section: t("section.operations", "Operations"), title: t("nav.picking", "Picking"), previous: "/inventory", next: "/shipping" },
    "/shipping": { section: t("section.operations", "Operations"), title: t("nav.shipping", "Shipping"), previous: "/picking", next: "/billing" },
    "/billing": { section: t("section.operations", "Operations"), title: t("nav.billing", "Billing"), previous: "/shipping", next: "/clients" },
    "/clients": { section: t("section.masterData", "Master Data"), title: t("nav.clients", "Clients"), previous: "/billing", next: "/receiving-code-settings" },
    "/receiving-code-settings": { section: t("section.masterData", "Master Data"), title: t("nav.receivingCodeSettings", "Receiving Code Settings"), previous: "/clients", next: "/receiving-label-settings" },
    "/receiving-label-settings": { section: t("section.masterData", "Master Data"), title: t("nav.receivingLabelSettings", "Receiving Label Settings"), previous: "/receiving-code-settings", next: "/warehouses" },
    "/warehouses": { section: t("section.masterData", "Master Data"), title: t("nav.warehouses", "Warehouses"), previous: "/receiving-label-settings", next: "/skus" },
    "/skus": { section: t("section.masterData", "Master Data"), title: t("nav.skus", "SKUs"), previous: "/warehouses", next: "/users" },
    "/users": {
      section: role === "platform_admin" ? t("section.platformAdmin", "Platform Admin") : t("section.admin", "Admin"),
      title: t("nav.users", "Users"),
      previous: role === "platform_admin" ? null : "/skus",
      next: role === "platform_admin" ? "/workspaces" : "/warehouse-planner",
    },
    "/workspaces": {
      section: t("section.platformAdmin", "Platform Admin"),
      title: t("nav.workspaces", "Workspaces"),
      previous: "/users",
      next: null,
    },
    "/warehouse-planner": { section: t("section.masterData", "Master Data"), title: t("nav.warehousePlanner", "Warehouse Planner"), previous: "/users", next: "/migration" },
    "/migration": { section: t("section.planningImport", "Planning & Import"), title: t("nav.migration", "Migration"), previous: "/warehouse-planner", next: "/agent-console" },
    "/agent-console": { section: t("section.admin", "Admin"), title: t("nav.agentConsole", "Agent Console"), previous: "/migration", next: "/agent-settings" },
    "/agent-settings": { section: t("section.admin", "Admin"), title: t("nav.agentSettings", "Agent Settings"), previous: "/agent-console", next: "/agv" },
    "/agv": { section: t("section.operations", "Operations"), title: t("nav.agv", "AGV"), previous: "/agent-settings", next: "/dashboard" },
    "/pricing": { section: t("section.admin", "Admin"), title: t("nav.pricing", "Pricing"), previous: "/dashboard", next: "/subscription" },
    "/subscription": { section: t("section.admin", "Admin"), title: t("nav.subscription", "Subscription"), previous: "/pricing", next: "/setup" },
    "/setup": { section: t("section.admin", "Admin"), title: t("nav.setupWizard", "Setup Wizard"), previous: "/dashboard", next: "/receiving" },
    "/portal/dashboard": { section: t("section.clientPortal", "Client Portal"), title: t("nav.dashboard", "Dashboard"), previous: null, next: "/portal/inventory" },
    "/portal/inventory": { section: t("section.clientPortal", "Client Portal"), title: t("nav.inventory", "Inventory"), previous: "/portal/dashboard", next: "/portal/orders" },
    "/portal/orders": { section: t("section.clientPortal", "Client Portal"), title: t("nav.orders", "Orders"), previous: "/portal/inventory", next: "/portal/invoices" },
    "/portal/invoices": { section: t("section.clientPortal", "Client Portal"), title: t("nav.invoices", "Invoices"), previous: "/portal/orders", next: "/portal/dashboard" },
  } as const;

  const nav = (role === "client_viewer" ? clientNav : role === "platform_admin" ? platformNav : operatorNav).filter((item) => {
    if (role === "client_viewer") return true;
    if (role === "platform_admin") return true;
    const canUseAgentConsole =
      permissions.includes("*") ||
      permissions.includes("users.manage") ||
      permissions.includes("inbound_orders.manage") ||
      permissions.includes("inbound_orders.import") ||
      permissions.includes("receiving.execute") ||
      permissions.includes("outbound_orders.manage") ||
      permissions.includes("master_data.manage") ||
      permissions.includes("billing.manage") ||
      permissions.includes("planner.manage");
    if (item.to === "/users") return permissions.includes("*") || permissions.includes("users.manage");
    if (item.to === "/billing") return permissions.includes("*") || permissions.includes("billing.manage");
    if (item.to === "/receiving-code-settings" || item.to === "/receiving-label-settings") return permissions.includes("*") || permissions.includes("users.manage");
    if (item.to === "/agent-console") return canUseAgentConsole;
    if (item.to === "/agent-settings") return permissions.includes("*") || permissions.includes("users.manage");
    if (item.to === "/warehouse-planner" || item.to === "/agv") return permissions.includes("*") || permissions.includes("planner.manage");
    return true;
  });
  const filteredOperatorGroups = operatorNavGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => nav.some((navItem) => navItem.to === item.to)),
    }))
    .filter((group) => group.items.length > 0);
  const navGroups = role === "platform_admin" ? platformNavGroups : filteredOperatorGroups;
  const activeGroupId =
    navGroups.find((group) => group.items.some((item) => item.to === location.pathname))?.id ||
    navGroups[0]?.id ||
    "operations";
  const [openGroups, setOpenGroups] = useState<string[]>([activeGroupId]);
  const ensureGroupOpen = (groupId: string) =>
    setOpenGroups((current) => (current.includes(groupId) ? current : [...current, groupId]));
  const toggleGroup = (groupId: string) =>
    setOpenGroups((current) => (current.includes(groupId) ? current.filter((id) => id !== groupId) : [...current, groupId]));
  useEffect(() => {
    if (role !== "client_viewer" && activeGroupId) ensureGroupOpen(activeGroupId);
  }, [activeGroupId, role]);
  const dynamicMeta =
    location.pathname.startsWith("/receiving/orders/")
      ? {
          section: t("section.operations", "Operations"),
          title: t("receiving.detailPageTitle", "Inbound Order Detail"),
          previous: "/receiving",
          next: null,
        }
      : null;
  const meta = dynamicMeta || routeMeta[location.pathname as keyof typeof routeMeta];
  const currentNavPath = dynamicMeta ? "/receiving" : location.pathname;
  const currentNavIndex = nav.findIndex((item) => item.to === currentNavPath);
  const previousArea = currentNavIndex > 0 ? nav[currentNavIndex - 1] : null;
  const nextArea = currentNavIndex >= 0 && currentNavIndex < nav.length - 1 ? nav[currentNavIndex + 1] : null;
  const simplifyMobileMeta = location.pathname === "/dashboard";

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex h-[100dvh] w-full flex-col overflow-x-hidden bg-[#f3f3f3] pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)] text-[#222]">
      <header className="hidden h-12 shrink-0 items-center bg-[#5d6b8b] text-white shadow-[0_2px_8px_rgba(32,44,72,0.28)] md:flex">
        <div className="flex h-full w-[200px] items-center gap-3 border-r border-white/15 px-4">
          <Menu size={20} className="text-white/90" />
          <span className="text-lg font-semibold tracking-[-0.02em]">GreaterWMS</span>
        </div>
        <div className="flex min-w-0 flex-1 items-center justify-between gap-4 px-5">
          <div className="flex shrink-0 items-center gap-3 text-xs font-medium text-white/90">
            <span className="hidden lg:inline">{role === "client_viewer" ? "Client viewer" : role === "platform_admin" ? "Platform admin" : "Warehouse operator"}</span>
            <button
              type="button"
              onClick={handleLogout}
              aria-label={t("common.signOut", "Sign out")}
              className="inline-flex h-8 w-8 items-center justify-center border border-white/25 text-white transition hover:bg-white/15"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
      {/* Desktop sidebar */}
      <aside className="hidden w-[200px] border-r border-[#d2d2d2] bg-[#ededed] text-[#2d2d2d] md:flex md:flex-col">
        <nav className="flex-1 overflow-y-auto py-2">
          {role === "client_viewer" ? (
            nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 border-l-2 px-4 py-3 text-sm transition-colors",
                    isActive
                      ? "border-[#5d6b8b] bg-[#5d6b8b] text-white font-semibold"
                      : "border-transparent text-[#333] hover:bg-[#dedede]"
                  )
                }
              >
                <item.icon size={18} />
                {item.label}
              </NavLink>
            ))
          ) : (
            navGroups.map((group) => {
              const isOpen = openGroups.includes(group.id);
              const hasActiveChild = group.items.some((item) => item.to === location.pathname);
              return (
                <div key={group.id}>
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.id)}
                    className={clsx(
                      "flex w-full items-center justify-between border-t border-[#d6d6d6] px-4 py-3 text-left",
                      hasActiveChild ? "text-[#333]" : "text-[#666]"
                    )}
                  >
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em]">{group.label}</p>
                    </div>
                    <ChevronDown
                      size={16}
                      className={clsx("transition-transform", isOpen ? "rotate-180" : "rotate-0")}
                    />
                  </button>

                  {isOpen ? (
                    <div className="pb-1">
                      {group.items.map((item) => (
                        <NavLink
                          key={item.to}
                          to={item.to}
                          className={({ isActive }) =>
                            clsx(
                              "flex items-center gap-3 border-l-2 px-4 py-2.5 text-sm transition-colors",
                              isActive
                                ? "border-[#5d6b8b] bg-[#5d6b8b] text-white font-semibold"
                                : "border-transparent text-[#333] hover:bg-[#dedede]"
                            )
                          }
                        >
                          <item.icon size={18} />
                          {item.label}
                        </NavLink>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
        </nav>

        <button
          onClick={handleLogout}
          className="flex items-center gap-3 border-t border-[#d2d2d2] px-4 py-3 text-sm text-[#555] transition hover:bg-[#dedede] hover:text-[#222]"
        >
          <LogOut size={18} />
          {t("common.signOut", "Sign out")}
        </button>
      </aside>

      {/* Mobile header */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-w-0 items-center justify-between gap-2 border-b border-[#4c5977] bg-[#5d6b8b] px-3 py-2.5 text-white sm:px-4 sm:py-3 md:hidden">
          <h1 className="min-w-0 truncate text-base font-semibold text-white sm:text-lg">GreaterWMS</h1>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              aria-label={mobileOpen ? t("common.close", "Close") : t("common.openMenu", "Open menu")}
              title={mobileOpen ? t("common.close", "Close") : t("common.openMenu", "Open menu")}
              onClick={() => setMobileOpen(!mobileOpen)}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center border border-white/25 bg-white/10 text-white transition hover:bg-white/20"
            >
              {mobileOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </header>

        {/* Mobile nav dropdown */}
        {mobileOpen && (
          <nav className="max-h-[calc(100dvh-4rem)] space-y-1 overflow-x-hidden overflow-y-auto border-b border-[#d2d2d2] bg-[#ededed] p-2.5 sm:p-3 md:hidden">
            {role === "client_viewer" ? (
              nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) =>
                    clsx(
                      "flex min-w-0 items-center gap-3 border-l-2 px-4 py-3 text-sm",
                      isActive ? "border-[#5d6b8b] bg-[#5d6b8b] text-white" : "border-transparent text-[#333]"
                    )
                  }
                >
                  <item.icon size={18} className="shrink-0" />
                  <span className="min-w-0 truncate">{item.label}</span>
                </NavLink>
              ))
            ) : (
              navGroups.map((group) => {
                const isOpen = openGroups.includes(group.id);
                return (
                  <div key={group.id} className="overflow-hidden border border-[#d6d6d6] bg-[#f6f6f6]">
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.id)}
                      className="flex w-full min-w-0 items-center justify-between gap-3 px-4 py-3 text-left"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-[11px] font-semibold uppercase tracking-[0.16em] text-[#555] sm:tracking-[0.2em]">{group.label}</p>
                      </div>
                      <ChevronDown
                        size={16}
                        className={clsx("shrink-0 transition-transform", isOpen ? "rotate-180" : "rotate-0")}
                      />
                    </button>
                    {isOpen ? (
                      <div className="space-y-1 px-2 pb-2">
                        {group.items.map((item) => (
                          <NavLink
                            key={item.to}
                            to={item.to}
                            onClick={() => setMobileOpen(false)}
                            className={({ isActive }) =>
                              clsx(
                              "flex min-w-0 items-center gap-3 border-l-2 px-4 py-2.5 text-sm",
                                isActive ? "border-[#5d6b8b] bg-[#5d6b8b] text-white" : "border-transparent text-[#333]"
                              )
                            }
                          >
                            <item.icon size={18} className="shrink-0" />
                            <span className="min-w-0 truncate">{item.label}</span>
                          </NavLink>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </nav>
        )}

        {/* Subscription banner */}
        {role !== "platform_admin" ? <PaywallBanner /> : null}

        {/* Main content */}
        <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-[#f3f3f3] p-3 sm:p-4 md:p-5">
          <OfflineOutboxBanner />
          {meta && location.pathname !== "/dashboard" && (
            <div
              className={clsx(
                "mb-4 min-w-0 border border-[#d7d7d7] bg-white px-3.5 py-3 shadow-[0_2px_8px_rgba(0,0,0,0.06)] sm:px-5",
                simplifyMobileMeta && "hidden md:block"
              )}
            >
              <div className="md:hidden">
                <div className="flex min-w-0 flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-[#647480] sm:tracking-[0.18em]">
                  <Link to={homePath} className="transition hover:text-[#13212c]">
                    {t("common.home", "Home")}
                  </Link>
                  <ChevronRight size={12} />
                  <span>{meta.section}</span>
                  <ChevronRight size={12} />
                  <span className="min-w-0 break-words text-[#13212c]">{meta.title}</span>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <Link
                    to={homePath}
                    className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-2 text-sm font-medium text-[#13212c] transition hover:bg-white"
                  >
                    <CornerUpLeft size={14} className="shrink-0" />
                    <span className="min-w-0 truncate">{backHomeLabel}</span>
                  </Link>
                  <div className="flex w-full gap-2">
                    {previousArea ? (
                      <Link
                        to={previousArea.to}
                        className="inline-flex min-w-0 flex-1 items-center gap-2 rounded-full border border-[#13212c]/10 bg-white/65 px-3 py-2 text-sm font-medium text-[#13212c] transition hover:bg-white"
                      >
                        <ChevronLeft size={14} className="shrink-0" />
                        <span className="truncate">
                          {t("common.previousArea", "Previous")}: {previousArea.label}
                        </span>
                      </Link>
                    ) : null}
                    {nextArea ? (
                      <Link
                        to={nextArea.to}
                        className="inline-flex min-w-0 flex-1 items-center justify-end gap-2 rounded-full border border-[#13212c]/10 bg-white/65 px-3 py-2 text-sm font-medium text-[#13212c] transition hover:bg-white"
                      >
                        <span className="truncate text-right">
                          {t("common.nextArea", "Next")}: {nextArea.label}
                        </span>
                        <ChevronRight size={14} className="shrink-0" />
                      </Link>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="hidden md:flex md:flex-col md:gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-[#647480]">
                    <Link to={homePath} className="transition hover:text-[#13212c]">
                      {t("common.home", "Home")}
                    </Link>
                    <ChevronRight size={12} />
                    <span>{meta.section}</span>
                    <ChevronRight size={12} />
                    <span className="text-[#13212c]">{meta.title}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Link
                      to={homePath}
                      className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-2 text-sm font-medium text-[#13212c] transition hover:bg-white"
                    >
                      <CornerUpLeft size={14} />
                      {backHomeLabel}
                    </Link>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {previousArea ? (
                    <Link
                      to={previousArea.to}
                      className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white/65 px-3 py-2 text-sm font-medium text-[#13212c] transition hover:bg-white"
                    >
                      <ChevronLeft size={14} />
                      <span className="text-[#65737f]">{t("common.previousArea", "Previous")}</span>
                      <span>{previousArea.label}</span>
                    </Link>
                  ) : null}
                  {nextArea ? (
                    <Link
                      to={nextArea.to}
                      className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white/65 px-3 py-2 text-sm font-medium text-[#13212c] transition hover:bg-white"
                    >
                      <span className="text-[#65737f]">{t("common.nextArea", "Next")}</span>
                      <span>{nextArea.label}</span>
                      <ChevronRight size={14} />
                    </Link>
                  ) : null}
                </div>
              </div>
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
    </div>
  );
}

/**
 * GreaterWMS application shell.
 *
 * The migrated frontend deliberately keeps the legacy production geometry:
 * 56px top bar, 200px left drawer, flat menu items, and a compact grey work
 * surface. This is the visual contract for the staging preview and production
 * cutover, not a new marketing-style application frame.
 */

import {
  Apple,
  Bot,
  Boxes,
  ChevronDown,
  CircleUserRound,
  ClipboardCheck,
  ClipboardList,
  Database,
  FileDown,
  FileUp,
  Github,
  Home,
  Info,
  Languages,
  LayoutDashboard,
  Mail,
  Menu,
  Receipt,
  Settings,
  Truck,
  UserRound,
  Users,
  Warehouse,
  X,
} from "lucide-react";
import clsx from "clsx";
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { defaultRouteForRole, useAuthStore } from "../hooks/useAuth";

type NavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  separator?: boolean;
};

function canUseMailTask(permissions: string[]) {
  return permissions.includes("*") || permissions.includes("mailtask.execute") || permissions.includes("mailtask.manage");
}

function NavigationItem({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  return (
    <>
      {item.separator ? <div className="h-px bg-[#d2d2d2]" aria-hidden="true" /> : null}
      <NavLink
        to={item.to}
        onClick={onNavigate}
        className={({ isActive }) =>
          clsx(
            "flex h-12 items-center gap-4 border-l-0 px-4 text-[14px] font-normal transition-colors",
            isActive ? "bg-[#596782] text-white" : "text-[#252525] hover:bg-[#dedede]",
          )
        }
      >
        <item.icon size={21} strokeWidth={2.1} className="shrink-0" />
        <span className="truncate">{item.label}</span>
      </NavLink>
    </>
  );
}

export default function Layout() {
  const { role, permissions, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const homePath = defaultRouteForRole(role);

  const operatorNav: NavItem[] = [
    { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    ...(canUseMailTask(permissions) ? [{ to: "/mail2task", icon: Mail, label: "Mail2Task" }] : []),
    { to: "/receiving", icon: ClipboardList, label: "Inbound", separator: true },
    { to: "/shipping", icon: Truck, label: "Outbound" },
    { to: "/putaway", icon: ClipboardCheck, label: "Receiving" },
    { to: "/inventory", icon: Warehouse, label: "Inventory" },
    { to: "/billing", icon: Receipt, label: "Finance", separator: true },
    { to: "/skus", icon: Boxes, label: "GoodsList" },
    { to: "/clients", icon: Info, label: "Base Info" },
    { to: "/warehouses", icon: Settings, label: "Warehouse" },
    { to: "/users", icon: Users, label: "Staff", separator: true },
    { to: "/shipping", icon: UserRound, label: "Driver" },
    { to: "/shipping", icon: Truck, label: "Transport" },
    { to: "/migration", icon: FileUp, label: "Upload Center", separator: true },
    { to: "/migration", icon: FileDown, label: "Download Center" },
  ];

  const clientNav: NavItem[] = [
    { to: "/portal/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/portal/inventory", icon: Warehouse, label: "Inventory", separator: true },
    { to: "/portal/orders", icon: ClipboardList, label: "Orders" },
    { to: "/portal/invoices", icon: Receipt, label: "Invoices" },
  ];

  const nav = role === "client_viewer" ? clientNav : operatorNav;
  const isDashboardLike = location.pathname === "/dashboard" || location.pathname === "/mail2task";

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden bg-[#f3f3f3] text-[#222]">
      <header className="flex h-14 shrink-0 items-center bg-[#4f5e7e] text-white shadow-[0_2px_8px_rgba(32,44,72,0.35)] md:fixed md:inset-x-0 md:top-0 md:z-30">
        <div className="flex h-full w-[200px] shrink-0 items-center border-r border-white/15">
          <button
            type="button"
            aria-label="Toggle menu"
            title="Toggle menu"
            onClick={() => setMobileOpen((value) => !value)}
            className="inline-flex h-14 w-12 items-center justify-center text-white hover:bg-white/10 md:pointer-events-none"
          >
            {mobileOpen ? <X size={23} /> : <Menu size={23} />}
          </button>
          <span className="truncate pr-3 text-[20px] font-bold tracking-[-0.02em]">GreaterWMS</span>
        </div>

        <div className="flex min-w-0 flex-1 items-center justify-end gap-1 px-2 sm:gap-2 sm:px-4">
          <div className="hidden items-center gap-1 sm:flex">
            <button type="button" title="iOS app" className="inline-flex h-10 w-10 items-center justify-center rounded-full text-white hover:bg-white/10"><Apple size={23} /></button>
            <button type="button" title="Android app" className="inline-flex h-10 w-10 items-center justify-center rounded-full text-white hover:bg-white/10"><Bot size={23} /></button>
            <button type="button" title="GitHub" className="inline-flex h-10 w-10 items-center justify-center rounded-full text-white hover:bg-white/10"><Github size={23} /></button>
            <button type="button" title="API" className="inline-flex h-10 w-10 items-center justify-center rounded-full text-white hover:bg-white/10"><Database size={22} /></button>
            <button type="button" title="Warehouse" className="inline-flex h-10 w-10 items-center justify-center rounded-full text-white hover:bg-white/10"><Home size={23} /></button>
          </div>
          <span className="hidden truncate px-2 text-[14px] font-medium tracking-[0.01em] lg:inline">PEAK SMART LOGISTICS</span>
          <button type="button" title="Language" className="inline-flex h-10 w-10 items-center justify-center rounded-full text-white hover:bg-white/10"><Languages size={23} /></button>
          <div className="mx-1 h-8 w-px bg-white/25" />
          <button
            type="button"
            title="Sign out"
            onClick={handleLogout}
            className="inline-flex h-10 items-center gap-1 rounded px-1 text-white hover:bg-white/10"
          >
            <CircleUserRound size={28} />
            <ChevronDown size={16} />
          </button>
        </div>
      </header>

      <div className="flex min-h-0 w-full flex-1 flex-col md:pt-14">
        <aside className={clsx(
          "fixed bottom-0 left-0 top-14 z-20 w-[200px] border-r border-[#cfcfcf] bg-[#eeeeee] shadow-[4px_0_12px_rgba(0,0,0,0.08)] md:flex",
          mobileOpen ? "flex" : "hidden",
        )}>
          <nav className="w-full overflow-y-auto" aria-label="GreaterWMS navigation">
            {nav.map((item) => <NavigationItem key={`${item.to}-${item.label}`} item={item} onNavigate={() => setMobileOpen(false)} />)}
          </nav>
        </aside>

        <main className="min-h-0 min-w-0 flex-1 overflow-x-auto overflow-y-auto bg-[#f3f3f3] p-2 md:ml-[200px]">
          {!isDashboardLike && role !== "client_viewer" ? (
            <div className="mb-2 border border-[#d1d1d1] bg-white px-3 py-2 text-xs text-[#5f6670]">
              {location.pathname.replace(/^\//, "").replaceAll("/", " / ") || homePath}
            </div>
          ) : null}
          <Outlet />
        </main>
      </div>
    </div>
  );
}

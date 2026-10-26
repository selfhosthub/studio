// ui/widgets/layout/Sidebar.tsx

"use client";

import {
  Bell,
  Bot,
  Building2,
  FileImage,
  Home,
  ImagePlay,
  Key,
  PanelLeft,
  PlayCircle,
  Plug,
  Server,
  Settings,
  Shield,
  BookOpen,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { useUser } from "@/entities/user";
import { usePageVisibility } from "@/entities/page-visibility";

type TooltipPosition = { top: number; left: number };

const useCollapsedTooltip = (isCollapsed: boolean) => {
  const [position, setPosition] = useState<TooltipPosition | null>(null);

  const show = (e: React.SyntheticEvent<HTMLElement>) => {
    if (!isCollapsed) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setPosition({ top: rect.top + rect.height / 2, left: rect.right + 8 });
  };
  const hide = () => setPosition(null);
  const onKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
    if (e.key === "Escape") hide();
  };

  return {
    position: isCollapsed ? position : null,
    handlers: { onMouseEnter: show, onFocus: show, onMouseLeave: hide, onBlur: hide, onKeyDown },
  };
};

const CollapsedTooltip = ({ label, position }: { label: string; position: TooltipPosition | null }) =>
  position ? (
    <span
      role="tooltip"
      style={{ top: position.top, left: position.left }} // css-check-ignore -- anchored to the hovered icon
      className="fixed z-50 -translate-y-1/2 whitespace-nowrap rounded-md bg-gray-900 px-2 py-1 text-xs font-medium text-white shadow-lg pointer-events-none" // css-check-ignore -- tooltip surface
    >
      {label}
    </span>
  ) : null;

type NavItemProps = {
  href: string;
  icon: React.ReactNode;
  label: string;
  isActive?: boolean;
  isCollapsed?: boolean;
  isDarkMode?: boolean;
  prefetch?: boolean;
};

const NavItem = ({
  href,
  icon,
  label,
  isActive,
  isCollapsed = false,
  isDarkMode = false,
  prefetch,
}: NavItemProps) => {
  const tooltip = useCollapsedTooltip(isCollapsed);

  return (
    <>
    <Link
      href={href}
      prefetch={prefetch}
      aria-label={isCollapsed ? label : undefined}
      {...tooltip.handlers}
      className={`
        flex items-center gap-x-3 px-3 py-2.5 rounded-md text-sm font-medium relative
        ${
          isActive
            ? isDarkMode
              ? "bg-blue-900 text-blue-100" // css-check-ignore -- brand active state
              : "bg-blue-600 text-white" // css-check-ignore: brand active state
            : isDarkMode
              ? "text-muted hover:bg-surface"
              : "text-secondary hover:bg-surface"
        }
        ${isCollapsed ? "justify-center py-3" : ""}
      `}
    >
      <div className={`${isCollapsed ? "text-center w-6" : ""}`}>{icon}</div>
      <div className={`flex-1 flex items-center justify-between ${isCollapsed ? "hidden" : ""}`}>
        <span>{label}</span>
      </div>
    </Link>
    <CollapsedTooltip label={label} position={tooltip.position} />
    </>
  );
};

type SidebarProps = {
  isCollapsed?: boolean;
  setIsCollapsed?: (value: boolean) => void;
  isMobileOpen?: boolean;
  setIsMobileOpen?: (value: boolean) => void;
};

const Sidebar = ({
  isCollapsed = false,
  setIsCollapsed,
  isMobileOpen = false,
  setIsMobileOpen,
}: SidebarProps) => {
  const pathname = usePathname() || "";
  const { user, status } = useUser();
  const { isPageVisible } = usePageVisibility();
  const docsTooltip = useCollapsedTooltip(isCollapsed);
  const [isDarkMode, setIsDarkMode] = useState(false);

  const toggleSidebar = () => {
    if (setIsCollapsed) {
      setIsCollapsed(!isCollapsed);
    }
  };

  // While the mobile menu is open, Escape closes it and the page behind it does not scroll
  useEffect(() => {
    if (!isMobileOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsMobileOpen?.(false);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isMobileOpen, setIsMobileOpen]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsDarkMode(document.documentElement.classList.contains('dark'));

    const checkDarkMode = () => {
      setIsDarkMode(document.documentElement.classList.contains('dark'));
    };

    window.addEventListener('storage', checkDarkMode);
    window.addEventListener('theme-change', checkDarkMode);

    return () => {
      window.removeEventListener('storage', checkDarkMode);
      window.removeEventListener('theme-change', checkDarkMode);
    };
  }, []);

  return (
    <>
    {isMobileOpen && (
      <div
        data-testid="sidebar-backdrop"
        aria-hidden="true"
        onClick={() => setIsMobileOpen?.(false)}
        className="fixed inset-x-0 bottom-0 top-12 z-30 bg-black/50 md:hidden"
      />
    )}
    <div
      data-collapsed={isCollapsed}
      id="sidebar-container"
      onClick={(e) => {
        // A tapped link navigates; close the mobile drawer so the page shows
        if ((e.target as HTMLElement).closest('a')) setIsMobileOpen?.(false);
      }}
      className={`
        ${isDarkMode ? 'bg-card border-secondary' : 'bg-card border-primary'}
        border-r flex flex-col fixed top-12 h-[calc(100%-3rem)] overflow-x-hidden z-30
        ${isCollapsed ? "w-16" : "w-64"}
        ${isMobileOpen ? "block z-40" : "hidden md:block"}
        transition-all duration-300 ease-in-out
      `}
    >
      <div className={`flex items-center justify-end h-12 px-2 border-b ${isDarkMode ? 'border-secondary' : 'border-primary'}`}>
        <button
          data-testid="sidebar-collapse-toggle"
          onClick={toggleSidebar}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!isCollapsed}
          className={`p-1.5 rounded-md ${
            isDarkMode
              ? 'text-muted hover:text-muted hover:bg-surface'
              : 'text-secondary hover:text-secondary hover:bg-card'
          } ${isCollapsed ? "mx-auto" : ""}`}
        >
          <PanelLeft
            size={20}
            className={`transition-transform duration-300 ${isCollapsed ? "rotate-180" : ""}`}
          />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto overflow-x-hidden py-4 px-2">
        {/* Defer the role-dependent nav until the user resolves. Rendering it
            while status==='loading' would mount the org-user branch, then
            remount the super-admin branch on resolve - each remount re-fires
            Next.js link prefetches (the duplicate _rsc= storm). */}
        {status === "loading" ? null : (
        <div className="space-y-1">
          {/* Dashboard (all) */}
          <NavItem
            href="/dashboard"
            icon={<Home size={20} />}
            label="Dashboard"
            isActive={pathname === "/dashboard"}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
            prefetch={false}
          />

          {/* Workflows - super_admin→marketplace, org users→organization */}
          <NavItem
            href={user?.role === "super_admin" ? "/workflows/list?tab=marketplace" : "/workflows/list?tab=organization"}
            icon={<Workflow size={20} />}
            label="Workflows"
            isActive={pathname?.startsWith("/workflows") || false}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
            prefetch={false}
          />

          {/* Instances (user/admin) */}
          {user?.role !== "super_admin" && (
            <NavItem
              href="/instances/list"
              icon={<PlayCircle size={20} />}
              label="Instances"
              isActive={pathname?.startsWith("/instances") || false}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}

          {/* Files (user/admin) */}
          {user?.role !== "super_admin" && (
            <NavItem
              href="/files"
              icon={<FileImage size={20} />}
              label="Files"
              isActive={pathname === "/files"}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}

          {/* Providers (all - super_admin lands on marketplace) */}
          <NavItem
            href={user?.role === "super_admin" ? "/providers/list?tab=marketplace" : "/providers/list?tab=organization"}
            icon={<Plug size={20} />}
            label="Providers"
            isActive={pathname?.startsWith("/providers") || false}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
            prefetch={false}
          />

          {/* AI Prompts (all - super_admin lands on marketplace tab) */}
          <NavItem
            href={user?.role === "super_admin" ? "/ai-prompts/prompts/list?tab=marketplace" : "/ai-prompts/prompts/list?tab=organization"}
            icon={<Bot size={20} />}
            label="AI Prompts"
            isActive={pathname?.startsWith("/ai-prompts") || false}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
            prefetch={false}
          />

          {/* ComfyUI Marketplace (super_admin only) */}
          {user?.role === "super_admin" && (
            <NavItem
              href="/comfyui/marketplace?tab=marketplace"
              icon={<ImagePlay size={20} />}
              label="ComfyUI"
              isActive={pathname?.startsWith("/comfyui") || false}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}

          {/* Organization(s) - different link per role */}
          {user?.role === "super_admin" && (
            <NavItem
              href="/organizations/list"
              icon={<Building2 size={20} />}
              label="Organizations"
              isActive={pathname?.startsWith("/organizations") || false}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}
          {user?.role === "admin" && (
            <NavItem
              href="/organization/manage"
              icon={<Building2 size={20} />}
              label="Organization"
              isActive={pathname === "/organization/manage" || pathname?.startsWith("/organization/")}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}
          {user?.role === "user" && user?.org_id && (
            <NavItem
              href={`/organizations/${user.org_id}`}
              icon={<Building2 size={20} />}
              label="Organization"
              isActive={pathname === `/organizations/${user.org_id}`}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}

          {/* Audit Logs (admin + super_admin) */}
          {(user?.role === "admin" || user?.role === "super_admin") && (
            <NavItem
              href="/audit"
              icon={<Shield size={20} />}
              label="Audit Logs"
              isActive={pathname === "/audit"}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}

          {/* Secrets (all) */}
          <NavItem
            href={user?.role === "super_admin" ? "/secrets" : "/secrets?tab=providers"}
            icon={<Key size={20} />}
            label="Secrets"
            isActive={pathname?.startsWith("/secrets") || false}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
            prefetch={false}
          />

          {/* Notifications (all) */}
          <NavItem
            href="/notifications"
            icon={<Bell size={20} />}
            label="Notifications"
            isActive={pathname === "/notifications"}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
            prefetch={false}
          />

          {/* Settings (all) */}
          <NavItem
            href="/settings"
            icon={<Settings size={20} />}
            label="Settings"
            isActive={pathname?.startsWith("/settings") || false}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
            prefetch={false}
          />

          {/* Infrastructure (super_admin only) */}
          {user?.role === "super_admin" && (
            <NavItem
              href="/infrastructure"
              icon={<Server size={20} />}
              label="Infrastructure"
              isActive={pathname?.startsWith("/infrastructure") || false}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}
        </div>
        )}
      </div>

      {/* Bottom section - Documentation link */}
      <div className={`border-t ${isDarkMode ? 'border-secondary' : 'border-primary'} px-2 py-4`}>
        <Link
          href="/docs"
          prefetch={false}
          aria-label={isCollapsed ? "Documentation" : undefined}
          {...docsTooltip.handlers}
          className={`
            flex items-center gap-x-3 px-3 py-2.5 rounded-md text-sm font-medium
            ${isDarkMode
              ? "text-muted hover:bg-surface"
              : "text-secondary hover:bg-surface"
            }
            ${isCollapsed ? "justify-center py-3" : ""}
          `}
        >
          <div className={`${isCollapsed ? "text-center w-6" : ""}`}>
            <BookOpen size={20} />
          </div>
          <span className={`${isCollapsed ? "hidden" : ""}`}>
            Documentation
          </span>
        </Link>
        <CollapsedTooltip label="Documentation" position={docsTooltip.position} />
      </div>
    </div>
    </>
  );
};

export default Sidebar;

// ui/widgets/layout/Sidebar.tsx

"use client";

import {
  Bell,
  Bot,
  Building2,
  ChevronDown,
  ChevronRight,
  FileImage,
  Home,
  Key,
  LayoutTemplate,
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

type NavItemProps = {
  href: string;
  icon: React.ReactNode;
  label: string;
  isActive?: boolean;
  isCollapsed?: boolean;
  hasSubmenu?: boolean;
  isSubmenuOpen?: boolean;
  isDarkMode?: boolean;
  onClick?: () => void;
  prefetch?: boolean;
};

const NavItem = ({
  href,
  icon,
  label,
  isActive,
  isCollapsed = false,
  hasSubmenu = false,
  isSubmenuOpen = false,
  isDarkMode = false,
  onClick,
  prefetch,
}: NavItemProps) => {
  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    const sidebarElement = document.getElementById('sidebar-container');
    const isInCollapsedMode = sidebarElement?.getAttribute('data-collapsed') === 'true';

    const isHoverExpanded = isInCollapsedMode && sidebarElement &&
      (window.getComputedStyle(sidebarElement).width !== '64px' &&
       window.getComputedStyle(sidebarElement).width !== '4rem');

    if (hasSubmenu && onClick && (!isInCollapsedMode || isHoverExpanded)) {
      e.preventDefault();
      onClick();
      return;
    }

    if (isInCollapsedMode && isHoverExpanded && href !== '#') {
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('sidebar-close-submenus'));
      }, 50);
      return;
    }

    if (isInCollapsedMode && href !== '#') {
      if (hasSubmenu && !isHoverExpanded) {
        e.preventDefault();
        return;
      }
    }
  };

  return (
    <Link
      href={href}
      onClick={handleClick}
      prefetch={prefetch}
      className={`
        group flex items-center gap-x-3 px-3 py-2.5 rounded-md text-sm font-medium relative
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
        ${isCollapsed && hasSubmenu ? "hover:bg-opacity-80" : ""}
      `}
    >
      <div className={`${isCollapsed ? "text-center w-6" : ""}`}>{icon}</div>
      <div className={`flex-1 flex items-center justify-between ${isCollapsed ? "hidden group-hover:flex" : ""}`}>
        <span>{label}</span>
        {hasSubmenu && (
          <div className="text-muted">
            {isSubmenuOpen ? (
              <ChevronDown size={16} />
            ) : (
              <ChevronRight size={16} />
            )}
          </div>
        )}
      </div>
    </Link>
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
  const { user } = useUser();
  const { isPageVisible } = usePageVisibility();
  const [isHoverExpanded, setIsHoverExpanded] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(false);

  const toggleSidebar = () => {
    if (setIsCollapsed) {
      setIsCollapsed(!isCollapsed);
    }
  };

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
    <div
      data-collapsed={isCollapsed}
      id="sidebar-container"
      onMouseEnter={() => isCollapsed && setIsHoverExpanded(true)}
      onMouseLeave={() => isCollapsed && setIsHoverExpanded(false)}
      className={`
        ${isDarkMode ? 'bg-card border-secondary' : 'bg-card border-primary'}
        border-r flex flex-col fixed top-12 h-[calc(100%-3rem)] overflow-x-hidden z-30
        ${isCollapsed ? "w-16 group hover:w-64" : "w-64"}
        ${isMobileOpen ? "block z-40" : "hidden md:block"}
        transition-all duration-300 ease-in-out
      `}
    >
      <div className={`flex items-center justify-end h-12 px-2 border-b ${isDarkMode ? 'border-secondary' : 'border-primary'}`}>
        <button
          onClick={toggleSidebar}
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
        <div className="space-y-1">
          {/* Dashboard (all) */}
          <NavItem
            href="/dashboard"
            icon={<Home size={20} />}
            label="Dashboard"
            isActive={pathname === "/dashboard"}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
          />

          {/* Blueprints - visible when enabled by super-admin, or always for super-admins */}
          {(user?.role === "super_admin" || isPageVisible("blueprints")) && (
            <NavItem
              href="/blueprints"
              icon={<LayoutTemplate size={20} />}
              label="Blueprints"
              isActive={pathname?.startsWith("/blueprints") || false}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
              prefetch={false}
            />
          )}

          {/* Workflows - super_admin→marketplace, org users→organization */}
          <NavItem
            href={user?.role === "super_admin" ? "/workflows/list?tab=marketplace" : "/workflows/list?tab=organization"}
            icon={<Workflow size={20} />}
            label="Workflows"
            isActive={pathname?.startsWith("/workflows") || false}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
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
          />

          {/* AI Agents (all - super_admin lands on marketplace tab) */}
          <NavItem
            href={user?.role === "super_admin" ? "/ai-agents/prompts/list?tab=marketplace" : "/ai-agents/prompts/list?tab=organization"}
            icon={<Bot size={20} />}
            label="AI Agents"
            isActive={pathname?.startsWith("/ai-agents") || false}
            isCollapsed={isCollapsed}
            isDarkMode={isDarkMode}
            prefetch={false}
          />

          {/* Organization(s) - different link per role */}
          {user?.role === "super_admin" && (
            <NavItem
              href="/organizations/list"
              icon={<Building2 size={20} />}
              label="Organizations"
              isActive={pathname?.startsWith("/organizations") || false}
              isCollapsed={isCollapsed}
              isDarkMode={isDarkMode}
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
            isActive={pathname === "/settings"}
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
      </div>

      {/* Bottom section - Documentation link */}
      <div className={`border-t ${isDarkMode ? 'border-secondary' : 'border-primary'} px-2 py-4`}>
        <Link
          href={user?.role === "super_admin" ? "/docs/super-admin" : "/docs"}
          prefetch={false}
          className={`
            group flex items-center gap-x-3 px-3 py-2.5 rounded-md text-sm font-medium
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
          <span className={`${isCollapsed ? "hidden group-hover:inline" : ""}`}>
            Documentation
          </span>
        </Link>
      </div>
    </div>
  );
};

export default Sidebar;

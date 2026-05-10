// ui/widgets/layout/DashboardLayout.tsx


'use client';

import { useState, useEffect } from 'react';
import Navbar from './Navbar';
import Sidebar from './Sidebar';
import Footer from './Footer';
import { MaintenanceBanner } from '@/features/maintenance';
import { usePreferences } from '@/entities/preferences';
import { useMaintenance } from '@/features/maintenance';
import { useNotificationWebSocket } from '@/features/notifications';
import { EntitlementTokenBanner } from '@/features/entitlement';
import { CatalogStatusProvider } from '@/features/marketplace';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { preferences, updatePreference } = usePreferences();

  // Get maintenance events from authenticated WebSocket (for all logged-in users)
  const { lastMaintenanceEvent } = useNotificationWebSocket();

  // Use maintenance hook with authenticated WebSocket events
  const { maintenanceMode, warningMode, warningUntil, reason } = useMaintenance({
    maintenanceEvent: lastMaintenanceEvent,
  });

  // If maintenance mode is enabled, redirect to maintenance page
  useEffect(() => {
    if (maintenanceMode) {
      window.location.href = '/maintenance';
    }
  }, [maintenanceMode]);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(preferences.sidebarCollapsed);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Update preferences when sidebar state changes
  const handleSidebarCollapse = (collapsed: boolean) => {
    setIsSidebarCollapsed(collapsed);
    updatePreference('sidebarCollapsed', collapsed);
  };

  // Sync with preferences on mount
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsSidebarCollapsed(preferences.sidebarCollapsed);
  }, [preferences.sidebarCollapsed]);

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  return (
    <div className="flex flex-col min-h-screen bg-card">
      <Navbar onMobileMenuToggle={toggleMobileMenu} />

      <Sidebar 
        isCollapsed={isSidebarCollapsed} 
        setIsCollapsed={handleSidebarCollapse}
        isMobileOpen={isMobileMenuOpen}
        setIsMobileOpen={setIsMobileMenuOpen}
      />

      <main
        className={`relative z-0 flex-grow transition-all duration-300 pt-12
          text-primary overflow-x-hidden
          ${isSidebarCollapsed ? 'md:ml-16' : 'md:ml-64'}`}
      >
        {/* Maintenance warning banner - inside main content area */}
        {warningMode && warningUntil && (
          <MaintenanceBanner warningUntil={warningUntil} reason={reason} />
        )}

        {/* Entitlement token nudge for super-admins */}
        <EntitlementTokenBanner />

        <CatalogStatusProvider>
          <div className="px-2 py-2">
            {children}
          </div>
        </CatalogStatusProvider>
      </main>

      <div className={`transition-all duration-300 ${
        isSidebarCollapsed ? 'md:ml-16' : 'md:ml-64'
      }`}>
        <Footer />
      </div>
    </div>
  );
}

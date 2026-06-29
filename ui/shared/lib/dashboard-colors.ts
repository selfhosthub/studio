// ui/shared/lib/dashboard-colors.ts

// Dashboard UI system colors - fixed semantic palette, not influenced by branding.
// Override via NEXT_PUBLIC_DASHBOARD_* env vars at build time.

export const DASHBOARD_COLORS = {
  primary: process.env.NEXT_PUBLIC_DASHBOARD_PRIMARY || '#3B82F6',
  primaryHover: process.env.NEXT_PUBLIC_DASHBOARD_PRIMARY_HOVER || '#2563EB',
  success: process.env.NEXT_PUBLIC_DASHBOARD_SUCCESS || '#10B981',
  danger: process.env.NEXT_PUBLIC_DASHBOARD_DANGER || '#EF4444',
  warning: process.env.NEXT_PUBLIC_DASHBOARD_WARNING || '#F59E0B',
  accent: process.env.NEXT_PUBLIC_DASHBOARD_ACCENT || '#10B981',
} as const;

/**
 * Inline script to inject dashboard color CSS variables before React hydration.
 * Added to <head> in layout.tsx to prevent color flash.
 */
export const dashboardColorScript = `
  (function() {
    var root = document.documentElement;
    root.style.setProperty('--theme-primary', '${DASHBOARD_COLORS.primary}');
    root.style.setProperty('--primary', '${DASHBOARD_COLORS.primary}');
    root.style.setProperty('--theme-btn-primary-bg', '${DASHBOARD_COLORS.primary}');
    root.style.setProperty('--theme-btn-primary-hover', '${DASHBOARD_COLORS.primaryHover}');
    root.style.setProperty('--theme-accent', '${DASHBOARD_COLORS.accent}');
    root.style.setProperty('--accent', '${DASHBOARD_COLORS.accent}');
    root.style.setProperty('--theme-success', '${DASHBOARD_COLORS.success}');
    root.style.setProperty('--theme-danger', '${DASHBOARD_COLORS.danger}');
    root.style.setProperty('--theme-warning', '${DASHBOARD_COLORS.warning}');
  })();
`;

// ui/widgets/layout/index.ts

// Navigation
export { default as Navbar } from './Navbar';
export { default as Sidebar } from './Sidebar';
export { default as Footer } from './Footer';
export { default as PublicNavbar } from './PublicNavbar';
export { default as PublicFooter } from './PublicFooter';

// Layout containers
export { default as DashboardLayout } from './DashboardLayout';
export { default as ListPageLayout } from './ListPageLayout';
export { default as ClientRootLayout } from './ClientRootLayout';

// Auth guards
export { ProtectedRoute } from './ProtectedRoute';
export { PageVisibilityGuard } from './PageVisibilityGuard';
export { default as DarkModeToggle } from './DarkModeToggle';

// Forms
export { default as BrandingSettingsForm } from './BrandingSettingsForm';

// Landing page
export { default as Features } from './Features';
export { default as Hero } from './Hero';
export { default as Testimonials } from './Testimonials';
export { default as AdminBrandingBanner } from './AdminBrandingBanner';

// Banners (re-exported from features)
export { MaintenanceBanner } from '@/features/maintenance';

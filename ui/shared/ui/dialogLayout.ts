// ui/shared/ui/dialogLayout.ts

/** Positions a dialog panel: top-aligned with a small margin below sm, centered from sm up. */
export const DIALOG_WRAPPER_CLASS = 'fixed inset-0 flex items-start sm:items-center justify-center p-4';

/** Caps a dialog panel at the dynamic viewport height minus the wrapper margins. */
export const DIALOG_PANEL_HEIGHT_CLASS = 'max-h-full max-h-[calc(100dvh-2rem)]';

/** Scrolls a dialog body inside the panel without scrolling the page behind it. */
export const DIALOG_SCROLL_CLASS = 'overflow-y-auto overscroll-contain';

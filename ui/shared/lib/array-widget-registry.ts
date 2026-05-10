// ui/shared/lib/array-widget-registry.ts

// Registry for array field widgets keyed by the `ui.widget` schema property.

import { ComponentType } from 'react';

const widgetRegistry = new Map<string, ComponentType<any>>();

const warnedWidgets = new Set<string>();

export function registerArrayWidget(name: string, component: ComponentType<any>): void {
  if (widgetRegistry.has(name)) {
    console.warn(`[ArrayWidgetRegistry] Overwriting existing widget: "${name}"`);
  }
  widgetRegistry.set(name, component);
}

export function getArrayWidget(name: string | undefined): ComponentType<any> | null {
  if (!name) {
    return null;
  }

  const widget = widgetRegistry.get(name);

  if (!widget && !warnedWidgets.has(name)) {
    console.warn(
      `[ArrayWidgetRegistry] Unknown array widget: "${name}". ` +
      `Falling back to default array renderer. ` +
      `Register the widget with registerArrayWidget() to use it.`
    );
    warnedWidgets.add(name);
  }

  return widget || null;
}

export function getRegisteredWidgets(): string[] {
  return Array.from(widgetRegistry.keys());
}

export function clearWidgetRegistry(): void {
  widgetRegistry.clear();
  warnedWidgets.clear();
}

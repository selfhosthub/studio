// ui/widgets/instance-view/InstanceSimpleView/hooks/useResizablePanel.ts

import { useState, useEffect, useRef, useCallback } from "react";
import { INSTANCE_DEFAULTS } from "@/shared/defaults";

interface UseResizablePanelOptions {
  /** localStorage key for persisting width */
  storageKey: string;
  /** Default panel width in pixels */
  defaultWidth?: number;
  /** Minimum allowed width */
  minWidth?: number;
  /** Maximum allowed width */
  maxWidth?: number;
  /** Breakpoint in px above which panel is resizable (side-by-side layout) */
  breakpoint?: number;
}

interface UseResizablePanelReturn {
  panelWidth: number;
  isLargeScreen: boolean;
  containerRef: React.RefObject<HTMLDivElement>;
  handleMouseDown: (e: React.MouseEvent) => void;
}

/**
 * Manages a resizable panel with mouse drag, window resize detection,
 * and localStorage persistence.
 */
export function useResizablePanel({
  storageKey,
  defaultWidth = INSTANCE_DEFAULTS.panelWidth,
  minWidth = INSTANCE_DEFAULTS.panelMinWidth,
  maxWidth = INSTANCE_DEFAULTS.panelMaxWidth,
  breakpoint = INSTANCE_DEFAULTS.panelBreakpoint,
}: UseResizablePanelOptions): UseResizablePanelReturn {
  const [panelWidth, setPanelWidth] = useState(() => {
    if (typeof window === "undefined") return defaultWidth;
    const saved = localStorage.getItem(storageKey);
    return saved ? parseInt(saved, 10) : defaultWidth;
  });
  const [isLargeScreen, setIsLargeScreen] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth >= breakpoint : false
  );
  const isResizing = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null) as React.RefObject<HTMLDivElement>;

  // Track window resize for responsive breakpoint
  useEffect(() => {
    const handleResize = () => setIsLargeScreen(window.innerWidth >= breakpoint);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [breakpoint]);

  // Persist width changes
  useEffect(() => {
    localStorage.setItem(storageKey, String(panelWidth));
  }, [storageKey, panelWidth]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isResizing.current || !containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const newWidth = e.clientX - containerRect.left;
      setPanelWidth(Math.max(minWidth, Math.min(maxWidth, newWidth)));
    },
    [minWidth, maxWidth]
  );

  const handleMouseUp = useCallback(() => {
    isResizing.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  useEffect(() => {
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  return { panelWidth, isLargeScreen, containerRef, handleMouseDown };
}

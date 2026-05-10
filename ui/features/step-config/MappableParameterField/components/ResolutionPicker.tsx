// ui/features/step-config/MappableParameterField/components/ResolutionPicker.tsx

'use client';

import React, { useState, useMemo } from 'react';
import { Lock, Unlock } from 'lucide-react';

interface ResolutionPickerProps {
  width: number;
  height: number;
  onWidthChange: (w: number) => void;
  onHeightChange: (h: number) => void;
  minValue?: number;
  maxValue?: number;
}

interface Preset {
  label: string;
  w: number;
  h: number;
}

const PRESETS: { category: string; items: Preset[] }[] = [
  {
    category: 'Landscape',
    items: [
      { label: 'HD 1080p', w: 1920, h: 1080 },
      { label: '720p', w: 1280, h: 720 },
      { label: '4K', w: 3840, h: 2160 },
      { label: '480p', w: 854, h: 480 },
    ],
  },
  {
    category: 'Portrait',
    items: [
      { label: 'TikTok / Reels', w: 1080, h: 1920 },
      { label: 'Portrait 720p', w: 720, h: 1280 },
      { label: 'Pinterest', w: 1000, h: 1500 },
    ],
  },
  {
    category: 'Square',
    items: [
      { label: '1080', w: 1080, h: 1080 },
      { label: '720', w: 720, h: 720 },
    ],
  },
];

const ASPECT_RATIOS = [
  { label: '16:9', w: 16, h: 9 },
  { label: '9:16', w: 9, h: 16 },
  { label: '4:3', w: 4, h: 3 },
  { label: '3:4', w: 3, h: 4 },
  { label: '1:1', w: 1, h: 1 },
  { label: '2:3', w: 2, h: 3 },
  { label: '3:2', w: 3, h: 2 },
  { label: '21:9', w: 21, h: 9 },
];

function gcd(a: number, b: number): number {
  a = Math.abs(a);
  b = Math.abs(b);
  while (b) {
    [a, b] = [b, a % b];
  }
  return a;
}

function getAspectRatioLabel(w: number, h: number): string {
  if (w <= 0 || h <= 0) return '';
  const d = gcd(w, h);
  const rw = w / d;
  const rh = h / d;
  // If the reduced ratio is in our known list, use it directly
  const known = ASPECT_RATIOS.find(r => r.w === rw && r.h === rh);
  if (known) return known.label;
  // For common ratios that don't reduce cleanly (e.g., 854x480 ≈ 16:9)
  const ratio = w / h;
  if (Math.abs(ratio - 16 / 9) < 0.02) return '~16:9';
  if (Math.abs(ratio - 9 / 16) < 0.02) return '~9:16';
  if (Math.abs(ratio - 4 / 3) < 0.02) return '~4:3';
  if (Math.abs(ratio - 3 / 4) < 0.02) return '~3:4';
  return `${rw}:${rh}`;
}

function snapToEven(n: number): number {
  return Math.round(n / 2) * 2;
}

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

export function ResolutionPicker({
  width,
  height,
  onWidthChange,
  onHeightChange,
  minValue = 100,
  maxValue = 3840,
}: ResolutionPickerProps) {
  const [lockedRatio, setLockedRatio] = useState<string>('');
  // Local input state so typing isn't interrupted by clamping
  const [localWidth, setLocalWidth] = useState<string>(String(width));
  const [localHeight, setLocalHeight] = useState<string>(String(height));

  // Sync local state when parent values change (e.g., from presets or ratio lock)
  // React-blessed pattern: adjust state during render when props change
  const [prevWidth, setPrevWidth] = useState(width);
  const [prevHeight, setPrevHeight] = useState(height);
  if (width !== prevWidth) {
    setPrevWidth(width);
    setLocalWidth(String(width));
  }
  if (height !== prevHeight) {
    setPrevHeight(height);
    setLocalHeight(String(height));
  }

  const aspectLabel = useMemo(() => getAspectRatioLabel(width, height), [width, height]);

  const isPresetActive = (p: Preset) => p.w === width && p.h === height;

  const selectPreset = (p: Preset) => {
    onWidthChange(p.w);
    onHeightChange(p.h);
    setLocalWidth(String(p.w));
    setLocalHeight(String(p.h));
    // Auto-set the lock to the preset's ratio
    const label = getAspectRatioLabel(p.w, p.h);
    const matchesKnown = ASPECT_RATIOS.find(r => r.label === label);
    setLockedRatio(matchesKnown ? label : '');
  };

  const getRatioMultipliers = (ratioLabel: string): { rw: number; rh: number } | null => {
    const r = ASPECT_RATIOS.find(a => a.label === ratioLabel);
    return r ? { rw: r.w, rh: r.h } : null;
  };

  // Commit width value (on blur or Enter)
  const commitWidth = () => {
    const parsed = parseInt(localWidth, 10);
    if (isNaN(parsed)) {
      setLocalWidth(String(width));
      return;
    }
    const w = clamp(parsed, minValue, maxValue);
    setLocalWidth(String(w));
    onWidthChange(w);
    if (lockedRatio) {
      const ratio = getRatioMultipliers(lockedRatio);
      if (ratio) {
        const h = clamp(snapToEven(w * ratio.rh / ratio.rw), minValue, maxValue);
        onHeightChange(h);
        setLocalHeight(String(h));
      }
    }
  };

  // Commit height value (on blur or Enter)
  const commitHeight = () => {
    const parsed = parseInt(localHeight, 10);
    if (isNaN(parsed)) {
      setLocalHeight(String(height));
      return;
    }
    const h = clamp(parsed, minValue, maxValue);
    setLocalHeight(String(h));
    onHeightChange(h);
    if (lockedRatio) {
      const ratio = getRatioMultipliers(lockedRatio);
      if (ratio) {
        const w = clamp(snapToEven(h * ratio.rw / ratio.rh), minValue, maxValue);
        onWidthChange(w);
        setLocalWidth(String(w));
      }
    }
  };

  const handleRatioChange = (ratioLabel: string) => {
    setLockedRatio(ratioLabel);
    if (ratioLabel) {
      // Recalculate height from current width
      const ratio = getRatioMultipliers(ratioLabel);
      if (ratio) {
        const h = clamp(snapToEven(width * ratio.rh / ratio.rw), minValue, maxValue);
        onHeightChange(h);
        setLocalHeight(String(h));
      }
    }
  };

  const toggleLock = () => {
    if (lockedRatio) {
      setLockedRatio('');
    } else {
      // Lock to current aspect ratio if it matches a known one
      const match = ASPECT_RATIOS.find(r => r.label === aspectLabel);
      setLockedRatio(match ? match.label : '');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent, commit: () => void) => {
    if (e.key === 'Enter') commit();
  };

  return (
    <div className="flex-1 space-y-3">
      {/* Presets */}
      <div className="space-y-1.5">
        {PRESETS.map(({ category, items }) => (
          <div key={category} className="flex items-center gap-1.5">
            <span className="text-[10px] text-muted dark:text-secondary w-16 shrink-0 text-right">{category}</span>
            <div className="flex gap-1 flex-wrap">
              {items.map((preset) => (
                <button
                  key={`${preset.w}x${preset.h}`}
                  type="button"
                  onClick={() => selectPreset(preset)}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    isPresetActive(preset)
                      ? 'bg-info text-white'
                      : 'bg-card text-secondary border border-primary hover:bg-input'
                  }`}
                  title={`${preset.w} x ${preset.h}`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Custom inputs + aspect ratio */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            value={localWidth}
            onChange={(e) => setLocalWidth(e.target.value)}
            onBlur={commitWidth}
            onKeyDown={(e) => handleKeyDown(e, commitWidth)}
            min={minValue}
            max={maxValue}
            step={2}
            className="w-20 p-1.5 border rounded text-sm text-center"
          />
          <span className="text-muted text-xs">x</span>
          <input
            type="number"
            value={localHeight}
            onChange={(e) => setLocalHeight(e.target.value)}
            onBlur={commitHeight}
            onKeyDown={(e) => handleKeyDown(e, commitHeight)}
            min={minValue}
            max={maxValue}
            step={2}
            className="w-20 p-1.5 border rounded text-sm text-center"
          />
        </div>

        {/* Aspect ratio badge */}
        {aspectLabel && (
          <span className="px-1.5 py-0.5 text-[10px] font-medium bg-card text-secondary rounded">
            {aspectLabel}
          </span>
        )}

        {/* Aspect ratio lock */}
        <div className="flex items-center gap-1 ml-auto">
          <select
            value={lockedRatio}
            onChange={(e) => handleRatioChange(e.target.value)}
            className="p-1 text-xs border rounded"
          >
            <option value="">No lock</option>
            {ASPECT_RATIOS.map((r) => (
              <option key={r.label} value={r.label}>{r.label}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={toggleLock}
            className={`p-1 rounded transition-colors ${
              lockedRatio
                ? 'text-info bg-info-subtle'
                : 'text-muted dark:text-secondary hover:text-secondary'
            }`}
            title={lockedRatio ? `Locked to ${lockedRatio}` : 'Lock aspect ratio'}
          >
            {lockedRatio ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
}

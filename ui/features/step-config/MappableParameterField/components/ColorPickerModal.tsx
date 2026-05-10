// ui/features/step-config/MappableParameterField/components/ColorPickerModal.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { Modal } from '@/shared/ui';
import { ColorPickerModalProps } from '../types';
import { FFMPEG_COLORS, RECENT_COLORS_KEY, MAX_RECENT_COLORS } from '../constants/colors';

/**
 * Color picker modal with transparency support
 * Supports FFmpeg named colors and recent colors
 */
export function ColorPickerModal({ value, onChange, placeholderColor }: ColorPickerModalProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [tempColor, setTempColor] = useState('#000000');
  const [tempAlpha, setTempAlpha] = useState(255); // 0-255
  const [recentColors, setRecentColors] = useState<string[]>([]);

  // When value is empty, show placeholderColor (inherited default) in the swatch
  const displayValue = value || placeholderColor || '';
  const isShowingPlaceholder = !value && !!placeholderColor;

  // Load recent colors from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(RECENT_COLORS_KEY);
      if (stored) {
        try {
          // eslint-disable-next-line react-hooks/set-state-in-effect -- initializing state from localStorage on mount; cannot use initializer since localStorage is unavailable during SSR
          setRecentColors(JSON.parse(stored));
        } catch {
          // Ignore parse errors
        }
      }
    }
  }, []);

  // Save color to recent colors
  const saveToRecentColors = (color: string) => {
    if (!color || color === '#000000') return; // Don't save default black

    setRecentColors(prev => {
      const filtered = prev.filter(c => c.toLowerCase() !== color.toLowerCase());
      const updated = [color, ...filtered].slice(0, MAX_RECENT_COLORS);
      if (typeof window !== 'undefined') {
        localStorage.setItem(RECENT_COLORS_KEY, JSON.stringify(updated));
      }
      return updated;
    });
  };

  // Parse color value to extract RGB and alpha
  const parseColor = (color: string): { hex: string; alpha: number } => {
    if (!color) return { hex: '#000000', alpha: 255 };

    const lowerColor = color.toLowerCase();

    // Check if it's a named color
    if (FFMPEG_COLORS[lowerColor]) {
      const namedHex = FFMPEG_COLORS[lowerColor];
      if (namedHex.length === 9) { // Has alpha (#RRGGBBAA)
        return {
          hex: namedHex.slice(0, 7),
          alpha: parseInt(namedHex.slice(7), 16)
        };
      }
      return { hex: namedHex, alpha: lowerColor === 'transparent' ? 0 : 255 };
    }

    // Handle hex values
    let hex = color.startsWith('#') ? color : `#${color}`;

    if (hex.length === 9) { // #RRGGBBAA
      return {
        hex: hex.slice(0, 7),
        alpha: parseInt(hex.slice(7), 16)
      };
    }
    if (hex.length === 7) { // #RRGGBB
      return { hex, alpha: 255 };
    }

    return { hex: '#000000', alpha: 255 };
  };

  // Format color for output (with or without alpha)
  const formatColor = (hex: string, alpha: number): string => {
    if (alpha === 255) {
      return hex; // No alpha needed
    }
    const alphaHex = alpha.toString(16).padStart(2, '0');
    return `${hex}${alphaHex}`;
  };

  const openModal = () => {
    const { hex, alpha } = parseColor(value);
    setTempColor(hex);
    setTempAlpha(alpha);
    setIsOpen(true);
  };

  const applyColor = () => {
    const finalColor = formatColor(tempColor, tempAlpha);
    saveToRecentColors(finalColor);
    onChange(finalColor);
    setIsOpen(false);
  };

  // Apply a recent color
  const applyRecentColor = (color: string) => {
    const { hex, alpha } = parseColor(color);
    setTempColor(hex);
    setTempAlpha(alpha);
  };

  const cancelModal = () => {
    setIsOpen(false);
  };

  // Get named color if current temp values match one
  const getCurrentNamedColor = (): string => {
    const formatted = formatColor(tempColor, tempAlpha).toLowerCase();
    for (const [name, hex] of Object.entries(FFMPEG_COLORS)) {
      if (hex.toLowerCase() === formatted || hex.toLowerCase() === tempColor.toLowerCase()) {
        if (name === 'transparent' && tempAlpha !== 0) continue;
        if (name !== 'transparent' && tempAlpha !== 255) continue;
        return name;
      }
    }
    return '';
  };

  // Checkerboard pattern for transparency visualization (css-check-ignore: visual rendering, not theming)
  const checkerboardStyle = (size: number) => ({
    backgroundImage: 'linear-gradient(45deg, #ccc 25%, transparent 25%), linear-gradient(-45deg, #ccc 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #ccc 75%), linear-gradient(-45deg, transparent 75%, #ccc 75%)',
    backgroundSize: `${size * 2}px ${size * 2}px`,
    backgroundPosition: `0 0, 0 ${size}px, ${size}px -${size}px, -${size}px 0px`,
  });

  return (
    <>
      {/* Color swatch button */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={openModal}
          className={`relative w-10 h-8 rounded cursor-pointer overflow-hidden${isShowingPlaceholder ? 'border-2 border-dashed border-secondary' : 'border'}`}
          title={isShowingPlaceholder ? `Default: ${placeholderColor}` : 'Open color picker'}
          style={checkerboardStyle(4)}
        >
          <div
            className="absolute inset-0"
            style={{
              backgroundColor: parseColor(displayValue).hex,
              opacity: (isShowingPlaceholder ? 0.6 : 1) * parseColor(displayValue).alpha / 255,
            }}
          />
        </button>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 p-1.5 border rounded text-sm font-mono"
          placeholder={placeholderColor ? `Default: ${placeholderColor}` : '#000000 or color name'}
        />
      </div>

      {/* Modal */}
      <Modal isOpen={isOpen} onClose={cancelModal} size="sm" panelClassName="w-80 max-w-[90vw] bg-card rounded-lg shadow-xl transition duration-200 ease-out data-[closed]:opacity-0 data-[closed]:scale-95">
        <div className="p-4">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-medium">Color Picker</h3>
            <button
              type="button"
              onClick={cancelModal}
              className="text-secondary hover:text-secondary"
            >
              <X size={20} />
            </button>
          </div>

          {/* Color preview with checkerboard for transparency */}
          <div
            className="w-full h-16 rounded border mb-4 relative overflow-hidden"
            style={checkerboardStyle(8)}
          >
            <div
              className="absolute inset-0"
              style={{
                backgroundColor: tempColor,
                opacity: tempAlpha / 255,
              }}
            />
          </div>

          {/* Color picker + Named colors row */}
          <div className="flex gap-2 mb-4">
            <input
              type="color"
              value={tempColor}
              onChange={(e) => setTempColor(e.target.value)}
              className="w-12 h-10 p-0 border rounded cursor-pointer"
              title="Pick a color"
            />
            <select
              value={getCurrentNamedColor()}
              onChange={(e) => {
                if (e.target.value) {
                  const hex = FFMPEG_COLORS[e.target.value];
                  if (e.target.value === 'transparent') {
                    setTempColor('#000000');
                    setTempAlpha(0);
                  } else {
                    setTempColor(hex.slice(0, 7));
                    setTempAlpha(255);
                  }
                }
              }}
              className="flex-1 p-2 border rounded text-sm"
              title="FFmpeg named colors"
            >
              <option value="">Custom</option>
              {Object.keys(FFMPEG_COLORS).map(colorName => (
                <option key={colorName} value={colorName}>
                  {colorName.charAt(0).toUpperCase() + colorName.slice(1)}
                </option>
              ))}
            </select>
          </div>

          {/* Hex input */}
          <div className="mb-4">
            <label className="block text-sm text-secondary mb-1">Hex Value</label>
            <input
              type="text"
              value={tempColor}
              onChange={(e) => {
                let val = e.target.value;
                if (!val.startsWith('#')) val = '#' + val;
                if (/^#[0-9A-Fa-f]{0,6}$/.test(val)) {
                  setTempColor(val);
                }
              }}
              className="w-full p-2 border rounded text-sm font-mono"
              placeholder="#000000"
            />
          </div>

          {/* Opacity slider */}
          <div className="mb-4">
            <div className="flex justify-between text-sm text-secondary mb-1">
              <label>Opacity</label>
              <span>{Math.round(tempAlpha / 255 * 100)}%</span>
            </div>
            <div className="relative h-6 rounded border overflow-hidden"
              style={checkerboardStyle(4)}
            >
              <div
                className="absolute inset-0"
                style={{
                  background: `linear-gradient(to right, transparent, ${tempColor})`,
                }}
              />
              <input
                type="range"
                min="0"
                max="255"
                value={tempAlpha}
                onChange={(e) => setTempAlpha(parseInt(e.target.value))}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
            </div>
          </div>

          {/* Recent colors */}
          {recentColors.length > 0 && (
            <div className="mb-4">
              <label className="block text-sm text-secondary mb-2">Recent</label>
              <div className="grid grid-cols-6 gap-1">
                {recentColors.map((color, idx) => {
                  const { hex, alpha } = parseColor(color);
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => applyRecentColor(color)}
                      className="w-8 h-8 rounded border border-primary cursor-pointer overflow-hidden hover:ring-2 hover:ring-blue-500"
                      title={color}
                      style={checkerboardStyle(3)}
                    >
                      <div
                        className="w-full h-full"
                        style={{
                          backgroundColor: hex,
                          opacity: alpha / 255,
                        }}
                      />
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={cancelModal}
              className="flex-1 px-4 py-2 border rounded text-secondary hover:bg-card"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={applyColor}
              className="btn-primary flex-1"
            >
              Apply
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}

export default ColorPickerModal;

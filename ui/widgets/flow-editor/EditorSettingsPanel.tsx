// ui/widgets/flow-editor/EditorSettingsPanel.tsx

'use client';

import React from 'react';
import { usePreferences } from '@/entities/preferences';

interface EditorSettingsPanelProps {
  onClose: () => void;
  showEditorHeight?: boolean;
  /** CSS class for the active toggle button. Defaults to 'bg-accent-primary text-white'. */
  activeButtonClass?: string;
  className?: string;
}

export function EditorSettingsPanel({
  onClose,
  showEditorHeight = false,
  activeButtonClass = 'bg-accent-primary text-white',
  className = '',
}: EditorSettingsPanelProps) {
  const { preferences, updatePreference } = usePreferences();

  const inactiveClass = 'bg-card text-secondary border border-secondary';

  return (
    <div className={`p-3 bg-surface rounded-md border border-primary ${className}`}>
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-sm font-medium text-primary">Quick Settings</h3>
        <button
          type="button"
          onClick={onClose}
          className="text-muted hover:text-secondary"
          title="Close Settings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
            <path fillRule="evenodd" d="M5.47 5.47a.75.75 0 011.06 0L12 10.94l5.47-5.47a.75.75 0 111.06 1.06L13.06 12l5.47 5.47a.75.75 0 11-1.06 1.06L12 13.06l-5.47 5.47a.75.75 0 01-1.06-1.06L10.94 12 5.47 6.53a.75.75 0 010-1.06z" clipRule="evenodd" />
          </svg>
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Editor Width */}
        <div>
          <label className="form-label text-xs">Editor Width</label>
          <div className="flex gap-2">
            {['centered', 'wide', 'full'].map((width) => (
              <button
                key={width}
                type="button"
                onClick={() => updatePreference('editorWidth', width as any)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.editorWidth === width ? activeButtonClass : inactiveClass
                }`}
              >
                {width.charAt(0).toUpperCase() + width.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Node Width */}
        <div>
          <label className="form-label text-xs">Node Width</label>
          <div className="flex gap-2">
            {['narrow', 'normal', 'wide'].map((width) => (
              <button
                key={width}
                type="button"
                onClick={() => updatePreference('nodeWidth', width as any)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.nodeWidth === width ? activeButtonClass : inactiveClass
                }`}
              >
                {width.charAt(0).toUpperCase() + width.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Node Spacing */}
        <div>
          <label className="form-label text-xs">Spacing (Horizontal)</label>
          <div className="flex gap-2">
            {['compact', 'normal', 'spacious'].map((spacing) => (
              <button
                key={spacing}
                type="button"
                onClick={() => updatePreference('nodeSpacing', spacing as any)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.nodeSpacing === spacing ? activeButtonClass : inactiveClass
                }`}
              >
                {spacing.charAt(0).toUpperCase() + spacing.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Edge Style */}
        <div>
          <label className="form-label text-xs">Connections</label>
          <div className="flex gap-2">
            {['bezier', 'straight', 'step'].map((style) => (
              <button
                key={style}
                type="button"
                onClick={() => updatePreference('edgeStyle', style as any)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.edgeStyle === style ? activeButtonClass : inactiveClass
                }`}
              >
                {style.charAt(0).toUpperCase() + style.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Backdrop Blur */}
        <div className="md:col-span-2">
          <label className="form-label text-xs">Panel Backdrop Blur</label>
          <div className="flex gap-2">
            {[
              { value: 'none', label: 'None' },
              { value: 'light', label: 'Light' },
              { value: 'heavy', label: 'Heavy' }
            ].map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => updatePreference('backdropBlur', value as any)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.backdropBlur === value ? activeButtonClass : inactiveClass
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="form-helper">Blur intensity when editing a step</p>
        </div>

        {/* Show Grid Toggle */}
        <div className="md:col-span-2">
          <label className="form-label text-xs">Show Grid</label>
          <div className="flex gap-2">
            {[
              { value: true, label: 'On' },
              { value: false, label: 'Off' }
            ].map(({ value, label }) => (
              <button
                key={String(value)}
                type="button"
                onClick={() => updatePreference('showGrid', value)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.showGrid === value ? activeButtonClass : inactiveClass
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="form-helper">Display grid in editor</p>
        </div>

        {/* Editor Height - only in embedded view */}
        {showEditorHeight && (
          <div className="md:col-span-4">
            <label className="form-label text-xs">
              Editor Height: {preferences.defaultEditorHeight}px
            </label>
            <input
              type="range"
              min="400"
              max="1000"
              step="50"
              value={preferences.defaultEditorHeight}
              onChange={(e) => updatePreference('defaultEditorHeight', parseInt(e.target.value))}
              className="w-full h-2 bg-input rounded-lg appearance-none cursor-pointer"
            />
          </div>
        )}
      </div>
    </div>
  );
}

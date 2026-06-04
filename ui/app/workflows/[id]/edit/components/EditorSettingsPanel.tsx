// ui/app/workflows/[id]/edit/components/EditorSettingsPanel.tsx

'use client';

import React from 'react';
import { usePreferences } from '@/entities/preferences';

interface EditorSettingsPanelProps {
  onClose: () => void;
  showEditorHeight?: boolean;
}

export function EditorSettingsPanel({ onClose, showEditorHeight = false }: EditorSettingsPanelProps) {
  const { preferences, updatePreference } = usePreferences();

  return (
    <div className={`${showEditorHeight ? 'mb-3' : 'mx-4 mt-4'} p-3 bg-surface rounded-md border border-primary`}>
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-sm font-medium text-primary">Quick Settings</h3>
        <button
          type="button"
          onClick={onClose}
          className="icon-muted"
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
          <p className="form-label text-xs">Editor Width</p>
          <div className="flex gap-2">
            {(['centered', 'wide', 'full'] as const).map((width) => (
              <button
                key={width}
                type="button"
                onClick={() => updatePreference('editorWidth', width)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.editorWidth === width
                    ? 'bg-blue-600 text-white' // css-check-ignore: no semantic token
                    : 'bg-card text-secondary border border-secondary'
                }`}
              >
                {width.charAt(0).toUpperCase() + width.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Node Width */}
        <div>
          <p className="form-label text-xs">Node Width</p>
          <div className="flex gap-2">
            {(['narrow', 'normal', 'wide'] as const).map((width) => (
              <button
                key={width}
                type="button"
                onClick={() => updatePreference('nodeWidth', width)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.nodeWidth === width
                    ? 'bg-blue-600 text-white' // css-check-ignore: no semantic token
                    : 'bg-card text-secondary border border-secondary'
                }`}
              >
                {width.charAt(0).toUpperCase() + width.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Node Spacing */}
        <div>
          <p className="form-label text-xs">Spacing (Horizontal)</p>
          <div className="flex gap-2">
            {(['compact', 'normal', 'spacious'] as const).map((spacing) => (
              <button
                key={spacing}
                type="button"
                onClick={() => updatePreference('nodeSpacing', spacing)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.nodeSpacing === spacing
                    ? 'bg-blue-600 text-white' // css-check-ignore: no semantic token
                    : 'bg-card text-secondary border border-secondary'
                }`}
              >
                {spacing.charAt(0).toUpperCase() + spacing.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Edge Style */}
        <div>
          <p className="form-label text-xs">Connections</p>
          <div className="flex gap-2">
            {(['bezier', 'straight', 'step'] as const).map((style) => (
              <button
                key={style}
                type="button"
                onClick={() => updatePreference('edgeStyle', style)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.edgeStyle === style
                    ? 'bg-blue-600 text-white' // css-check-ignore: no semantic token
                    : 'bg-card text-secondary border border-secondary'
                }`}
              >
                {style.charAt(0).toUpperCase() + style.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Backdrop Blur */}
        <div className="md:col-span-2">
          <p className="form-label text-xs">Panel Backdrop Blur</p>
          <div className="flex gap-2">
            {[
              { value: 'none' as const, label: 'None' },
              { value: 'light' as const, label: 'Light' },
              { value: 'heavy' as const, label: 'Heavy' }
            ].map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => updatePreference('backdropBlur', value)}
                className={`flex-1 px-2 py-1 text-xs rounded ${
                  preferences.backdropBlur === value
                    ? 'bg-blue-600 text-white' // css-check-ignore: no semantic token
                    : 'bg-card text-secondary border border-secondary'
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
          <p className="form-label text-xs">Show Grid</p>
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
                  preferences.showGrid === value
                    ? 'bg-blue-600 text-white' // css-check-ignore: no semantic token
                    : 'bg-card text-secondary border border-secondary'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="form-helper">Display grid in workflow editor</p>
        </div>

        {/* Editor Height - only in embedded view */}
        {showEditorHeight && (
          <div className="md:col-span-4">
            <p className="form-label text-xs">Editor Height</p>
            <div className="flex gap-2">
              {[
                { value: 400, label: '400px' },
                { value: 500, label: '500px' },
                { value: 600, label: '600px' },
                { value: 700, label: '700px' },
                { value: 850, label: '850px' },
                { value: 1000, label: '1000px' },
              ].map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => updatePreference('defaultEditorHeight', value)}
                  className={`flex-1 px-2 py-1 text-xs rounded ${
                    preferences.defaultEditorHeight === value
                      ? 'bg-blue-600 text-white' // css-check-ignore: no semantic token
                      : 'bg-card text-secondary border border-secondary'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

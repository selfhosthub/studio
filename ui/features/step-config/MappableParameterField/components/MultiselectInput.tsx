// ui/features/step-config/MappableParameterField/components/MultiselectInput.tsx

'use client';

import React, { useState } from 'react';
import { ChevronUp, ChevronDown, Star, Clock, Plus, X } from 'lucide-react';
import { MultiselectInputProps } from '../types';

/**
 * Multiselect input component for array of enum values (e.g., style presets)
 * Features: reorderable selected items, favorites, recently used, search
 */
export function MultiselectInput({ value, schema, paramKey, onValueChange }: MultiselectInputProps) {
  const currentValues = Array.isArray(value) ? value : [];
  const enumValues = schema.items?.enum || [];
  const enumNames = schema.items?.enumNames || enumValues;
  const [searchTerm, setSearchTerm] = useState('');

  // Favorites and recently used - stored in localStorage
  const storageKey = `multiselect_favorites_${paramKey}`;
  const recentKey = `multiselect_recent_${paramKey}`;

  const [favorites, setFavorites] = useState<string[]>(() => {
    if (typeof window === 'undefined') return [];
    try {
      return JSON.parse(localStorage.getItem(storageKey) || '[]');
    } catch {
      return [];
    }
  });

  const [recentlyUsed, setRecentlyUsed] = useState<string[]>(() => {
    if (typeof window === 'undefined') return [];
    try {
      return JSON.parse(localStorage.getItem(recentKey) || '[]');
    } catch {
      return [];
    }
  });

  // Get label for a value
  const getLabel = (val: string): string => {
    const idx = enumValues.indexOf(val);
    return idx >= 0 ? String(enumNames[idx] || val) : val;
  };

  // Toggle favorite
  const toggleFavorite = (val: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const newFavorites = favorites.includes(val)
      ? favorites.filter(f => f !== val)
      : [...favorites, val];
    setFavorites(newFavorites);
    localStorage.setItem(storageKey, JSON.stringify(newFavorites));
  };

  // Track recently used (max 10)
  const trackRecent = (val: string) => {
    const newRecent = [val, ...recentlyUsed.filter(r => r !== val)].slice(0, 10);
    setRecentlyUsed(newRecent);
    localStorage.setItem(recentKey, JSON.stringify(newRecent));
  };

  // Move item up in the order
  const moveUp = (index: number) => {
    if (index <= 0) return;
    const newValues = [...currentValues];
    [newValues[index - 1], newValues[index]] = [newValues[index], newValues[index - 1]];
    onValueChange(paramKey, newValues);
  };

  // Move item down in the order
  const moveDown = (index: number) => {
    if (index >= currentValues.length - 1) return;
    const newValues = [...currentValues];
    [newValues[index], newValues[index + 1]] = [newValues[index + 1], newValues[index]];
    onValueChange(paramKey, newValues);
  };

  // Remove item from selection
  const removeItem = (val: string) => {
    onValueChange(paramKey, currentValues.filter((v: string) => v !== val));
  };

  // Add item to selection
  const addItem = (val: string) => {
    trackRecent(val);
    onValueChange(paramKey, [...currentValues, val]);
  };

  // Filter available (unselected) options by search term
  const availableOptions = enumValues
    .map((option: string | number, idx: number) => ({
      value: String(option),
      label: String(enumNames[idx] || option),
    }))
    .filter(({ value: val }: { value: string }) => !currentValues.includes(val))
    .filter(({ value: val, label }: { value: string; label: string }) => {
      if (!searchTerm) return true;
      const term = searchTerm.toLowerCase();
      return val.toLowerCase().includes(term) || label.toLowerCase().includes(term);
    });

  // Get favorites that are available (not already selected)
  const availableFavorites = favorites
    .filter(f => enumValues.includes(f) && !currentValues.includes(f))
    .filter(f => {
      if (!searchTerm) return true;
      const label = getLabel(f);
      const term = searchTerm.toLowerCase();
      return f.toLowerCase().includes(term) || String(label).toLowerCase().includes(term);
    });

  // Get recently used that are available (not already selected, not in favorites)
  const availableRecent = recentlyUsed
    .filter(r => enumValues.includes(r) && !currentValues.includes(r) && !favorites.includes(r))
    .filter(r => {
      if (!searchTerm) return true;
      const label = getLabel(r);
      const term = searchTerm.toLowerCase();
      return r.toLowerCase().includes(term) || String(label).toLowerCase().includes(term);
    })
    .slice(0, 5); // Show max 5 recent

  // Filter out favorites and recent from main list
  const mainOptions = availableOptions.filter(
    ({ value: val }) => !favorites.includes(val) && !recentlyUsed.includes(val)
  );

  return (
    <div className="flex-1 border border-primary rounded-md bg-card overflow-hidden">
      {/* Selected items section - reorderable */}
      {currentValues.length > 0 && (
        <div className="border-b border-primary bg-info-subtle p-2">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-info uppercase tracking-wide">
              Selected ({currentValues.length})
            </span>
            <button
              type="button"
              onClick={() => onValueChange(paramKey, [])}
              className="text-xs text-danger hover:text-danger"
            >
              Clear all
            </button>
          </div>
          <div className="space-y-1">
            {currentValues.map((val: string, index: number) => (
              <div
                key={val}
                className="flex items-center gap-1 py-1 px-2 bg-card rounded border border-info"
              >
                {/* Order number */}
                <span className="w-5 h-5 flex items-center justify-center text-xs font-medium text-info bg-info-subtle rounded">
                  {index + 1}
                </span>
                {/* Label */}
                <span className="flex-1 text-sm text-secondary truncate">
                  {getLabel(val)}
                </span>
                {/* Favorite button */}
                <button
                  type="button"
                  onClick={(e) => toggleFavorite(val, e)}
                  className={`p-0.5${favorites.includes(val) ? 'text-warning' : 'text-muted hover:text-warning'}`}
                  title={favorites.includes(val) ? 'Remove from favorites' : 'Add to favorites'}
                >
                  <Star className="h-4 w-4" fill={favorites.includes(val) ? 'currentColor' : 'none'} />
                </button>
                {/* Reorder buttons */}
                <button
                  type="button"
                  onClick={() => moveUp(index)}
                  disabled={index === 0}
                  className="p-0.5 text-muted hover:text-secondary disabled:opacity-30 disabled:cursor-not-allowed"
                  title="Move up"
                >
                  <ChevronUp className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => moveDown(index)}
                  disabled={index === currentValues.length - 1}
                  className="p-0.5 text-muted hover:text-secondary disabled:opacity-30 disabled:cursor-not-allowed"
                  title="Move down"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
                {/* Remove button */}
                <button
                  type="button"
                  onClick={() => removeItem(val)}
                  className="p-0.5 text-danger hover:text-danger"
                  title="Remove"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Search filter - STICKY outside scrollable area */}
      {enumValues.length > 10 && (
        <div className="p-2 border-b border-primary bg-surface">
          <input
            type="text"
            placeholder="Search styles..."
            value={searchTerm}
            className="w-full px-3 py-2 border border-primary rounded-md text-sm"
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      )}

      {/* Available items section - scrollable */}
      <div className="p-2 max-h-48 overflow-y-auto">
        {/* Favorites section */}
        {availableFavorites.length > 0 && (
          <div className="mb-2">
            <div className="flex items-center gap-1 mb-1">
              <Star className="h-3 w-3 text-warning" fill="currentColor" />
              <span className="text-xs font-medium text-warning uppercase tracking-wide">
                Favorites
              </span>
            </div>
            <div className="space-y-1">
              {availableFavorites.map((val) => (
                <div
                  key={val}
                  role="button"
                  tabIndex={0}
                  onClick={() => addItem(val)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') addItem(val); }}
                  className="w-full flex items-center gap-2 py-1 px-2 rounded hover:bg-warning-subtle text-left bg-warning-subtle cursor-pointer"
                >
                  <Plus className="h-4 w-4 text-warning" />
                  <span className="flex-1 text-sm text-secondary">{getLabel(val)}</span>
                  <button
                    type="button"
                    onClick={(e) => toggleFavorite(val, e)}
                    className="p-0.5 text-warning hover:text-warning"
                    title="Remove from favorites"
                  >
                    <Star className="h-3 w-3" fill="currentColor" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recently used section */}
        {availableRecent.length > 0 && (
          <div className="mb-2">
            <div className="flex items-center gap-1 mb-1">
              <Clock className="h-3 w-3 text-muted" />
              <span className="text-xs font-medium text-secondary uppercase tracking-wide">
                Recent
              </span>
            </div>
            <div className="space-y-1">
              {availableRecent.map((val) => (
                <div
                  key={val}
                  role="button"
                  tabIndex={0}
                  onClick={() => addItem(val)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') addItem(val); }}
                  className="w-full flex items-center gap-2 py-1 px-2 rounded hover:bg-card text-left cursor-pointer"
                >
                  <Plus className="h-4 w-4 text-muted" />
                  <span className="flex-1 text-sm text-secondary">{getLabel(val)}</span>
                  <button
                    type="button"
                    onClick={(e) => toggleFavorite(val, e)}
                    className={`p-0.5${favorites.includes(val) ? 'text-warning' : 'text-muted hover:text-warning'}`}
                    title="Add to favorites"
                  >
                    <Star className="h-3 w-3" fill={favorites.includes(val) ? 'currentColor' : 'none'} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Divider if there are favorites/recent and main options */}
        {(availableFavorites.length > 0 || availableRecent.length > 0) && mainOptions.length > 0 && (
          <div className="border-t border-primary my-2" />
        )}

        {/* Main options */}
        {mainOptions.length > 0 ? (
          <div className="space-y-1">
            {mainOptions.map(({ value: optionValue, label }: { value: string; label: string }) => (
              <div
                key={optionValue}
                role="button"
                tabIndex={0}
                onClick={() => addItem(optionValue)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') addItem(optionValue); }}
                className="w-full flex items-center gap-2 py-1 px-2 rounded hover:bg-card text-left cursor-pointer"
              >
                <Plus className="h-4 w-4 text-muted" />
                <span className="flex-1 text-sm text-secondary">{label}</span>
                <button
                  type="button"
                  onClick={(e) => toggleFavorite(optionValue, e)}
                  className="p-0.5 text-muted hover:text-warning opacity-0 group-hover:opacity-100"
                  title="Add to favorites"
                >
                  <Star className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        ) : searchTerm && availableFavorites.length === 0 && availableRecent.length === 0 ? (
          <p className="text-sm text-secondary text-center py-2">
            No matches for &quot;{searchTerm}&quot;
          </p>
        ) : currentValues.length === enumValues.length ? (
          <p className="text-sm text-secondary text-center py-2">
            All styles selected
          </p>
        ) : null}
      </div>
    </div>
  );
}

export default MultiselectInput;

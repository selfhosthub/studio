// ui/features/step-config/HttpHeadersEditor.tsx

import React, { useState, useEffect, useRef } from 'react';

interface HttpHeader {
  id: string; // Unique ID for stable keys
  name: string;
  value: string;
}

interface HttpHeadersEditorProps {
  headers: Record<string, string>;
  onChange: (headers: Record<string, string>) => void;
}

// Standard HTTP headers for autocomplete
const COMMON_HTTP_HEADERS = [
  'Accept',
  'Accept-Charset',
  'Accept-Encoding',
  'Accept-Language',
  'Authorization',
  'Cache-Control',
  'Connection',
  'Content-Length',
  'Content-Type',
  'Cookie',
  'Date',
  'Host',
  'Origin',
  'Referer',
  'User-Agent',
  'X-API-Key',
  'X-Requested-With',
  'X-Forwarded-For',
  'X-Forwarded-Proto',
  'X-Correlation-ID',
];

// Common values for specific headers
const HEADER_VALUE_SUGGESTIONS: Record<string, string[]> = {
  'Content-Type': [
    'application/json',
    'application/xml',
    'application/x-www-form-urlencoded',
    'multipart/form-data',
    'text/plain',
    'text/html',
  ],
  'Accept': [
    'application/json',
    'application/xml',
    'text/plain',
    'text/html',
    '*/*',
  ],
  'Cache-Control': [
    'no-cache',
    'no-store',
    'max-age=0',
    'max-age=3600',
    'public',
    'private',
  ],
  'Connection': [
    'keep-alive',
    'close',
  ],
};

export default function HttpHeadersEditor({ headers = {}, onChange }: HttpHeadersEditorProps) {
  const [headersList, setHeadersList] = useState<HttpHeader[]>([]);
  const [initialized, setInitialized] = useState(false);

  // Autocomplete states
  const [showNameSuggestions, setShowNameSuggestions] = useState<{id: string, suggestions: string[]}>({id: '', suggestions: []});
  const [showValueSuggestions, setShowValueSuggestions] = useState<{id: string, suggestions: string[]}>({id: '', suggestions: []});
  const suggestionContainerRef = useRef<HTMLDivElement>(null);

  // Initialize with default headers or convert existing ones on component mount
  useEffect(() => {
    if (!initialized) {
      let initialHeaders: HttpHeader[] = [];

      // If headers object is empty, add default Content-Type header
      if (Object.keys(headers).length === 0) {
        initialHeaders = [
          { id: generateId(), name: 'Content-Type', value: 'application/json' }
        ];

        // Update parent with default header
        const defaultHeaders: Record<string, string> = {};
        initialHeaders.forEach(h => {
          if (h.name && h.value) {
            defaultHeaders[h.name] = h.value;
          }
        });
        onChange(defaultHeaders);
      } else {
        // Convert existing headers object to array with IDs
        initialHeaders = Object.entries(headers).map(([name, value]) => ({
          id: generateId(),
          name,
          value
        }));
      }

      setHeadersList(initialHeaders);
      setInitialized(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally runs once on mount
  }, []);

  // Generate unique ID for stable list keys
  const generateId = () => {
    return Math.random().toString(36).substring(2, 9);
  };

  // Update the parent component with new headers
  const updateHeaders = (newHeadersList: HttpHeader[]) => {
    const newHeaders: Record<string, string> = {};

    // Only include headers with both name and value
    newHeadersList.forEach(header => {
      if (header.name && header.value) {
        newHeaders[header.name] = header.value;
      }
    });

    onChange(newHeaders);
  };

  // Close suggestion dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (suggestionContainerRef.current && !suggestionContainerRef.current.contains(event.target as Node)) {
        setShowNameSuggestions({id: '', suggestions: []});
        setShowValueSuggestions({id: '', suggestions: []});
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Handle header input changes and trigger autocomplete
  const handleHeaderChange = (id: string, field: 'name' | 'value', value: string) => {
    const newHeadersList = headersList.map(header =>
      header.id === id ? { ...header, [field]: value } : header
    );

    // Update state
    setHeadersList(newHeadersList);
    updateHeaders(newHeadersList);

    // Show autocomplete suggestions if appropriate
    if (field === 'name' && value) {
      const suggestions = COMMON_HTTP_HEADERS.filter(
        h => h.toLowerCase().includes(value.toLowerCase())
      );

      if (suggestions.length > 0) {
        setShowNameSuggestions({ id, suggestions });
        setShowValueSuggestions({ id: '', suggestions: [] });
      } else {
        setShowNameSuggestions({ id: '', suggestions: [] });
      }
    }
    else if (field === 'value') {
      // Get the header name to find relevant value suggestions
      const headerName = newHeadersList.find(h => h.id === id)?.name || '';

      if (headerName && HEADER_VALUE_SUGGESTIONS[headerName]) {
        const suggestions = HEADER_VALUE_SUGGESTIONS[headerName].filter(
          v => v.toLowerCase().includes(value.toLowerCase())
        );

        if (suggestions.length > 0) {
          setShowValueSuggestions({ id, suggestions });
        } else {
          setShowValueSuggestions({ id: '', suggestions: [] });
        }
      }
    }
  };

  // Handle selecting a suggestion
  const handleSelectSuggestion = (id: string, field: 'name' | 'value', suggestion: string) => {
    handleHeaderChange(id, field, suggestion);

    // Close the suggestions
    if (field === 'name') {
      setShowNameSuggestions({ id: '', suggestions: [] });

      // If there are value suggestions for this header, show them
      if (HEADER_VALUE_SUGGESTIONS[suggestion]) {
        setShowValueSuggestions({
          id,
          suggestions: HEADER_VALUE_SUGGESTIONS[suggestion]
        });
      }
    } else {
      setShowValueSuggestions({ id: '', suggestions: [] });
    }
  };

  const addHeader = () => {
    const newHeader = { id: generateId(), name: '', value: '' };
    const newHeadersList = [...headersList, newHeader];
    setHeadersList(newHeadersList);
  };

  const removeHeader = (id: string) => {
    const newHeadersList = headersList.filter(header => header.id !== id);

    // Ensure there's always at least one row
    if (newHeadersList.length === 0) {
      newHeadersList.push({ id: generateId(), name: '', value: '' });
    }

    setHeadersList(newHeadersList);
    updateHeaders(newHeadersList);
  };

  return (
    <div className="space-y-2" ref={suggestionContainerRef}>
      {headersList.map((header) => (
        <div key={header.id} className="relative">
          <div className="flex gap-2 items-center">
            <div className="flex-1 min-w-0 relative">
              <input
                type="text"
                value={header.name}
                onChange={(e) => handleHeaderChange(header.id, 'name', e.target.value)}
                placeholder="Header name"
                className="w-full px-3 py-2 border border-primary rounded-md text-sm"
                autoComplete="off"
              />

              {/* Name suggestions dropdown */}
              {showNameSuggestions.id === header.id && showNameSuggestions.suggestions.length > 0 && (
                <div className="absolute z-10 mt-1 w-full bg-card shadow-lg max-h-60 rounded-md overflow-auto border border-primary">
                  <ul className="py-1 text-sm">
                    {showNameSuggestions.suggestions.map((suggestion) => (
                      <li
                        key={suggestion}
                        className="px-3 py-2 hover:bg-surface cursor-pointer text-primary"
                        onClick={() => handleSelectSuggestion(header.id, 'name', suggestion)}
                      >
                        {suggestion}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="flex-1 min-w-0 relative">
              <input
                type="text"
                value={header.value}
                onChange={(e) => handleHeaderChange(header.id, 'value', e.target.value)}
                placeholder="Value"
                className="w-full px-3 py-2 border border-primary rounded-md text-sm"
                autoComplete="off"
              />

              {/* Value suggestions dropdown */}
              {showValueSuggestions.id === header.id && showValueSuggestions.suggestions.length > 0 && (
                <div className="absolute z-10 mt-1 w-full bg-card shadow-lg max-h-60 rounded-md overflow-auto border border-primary">
                  <ul className="py-1 text-sm">
                    {showValueSuggestions.suggestions.map((suggestion) => (
                      <li
                        key={suggestion}
                        className="px-3 py-2 hover:bg-surface cursor-pointer text-primary"
                        onClick={() => handleSelectSuggestion(header.id, 'value', suggestion)}
                      >
                        {suggestion}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => removeHeader(header.id)}
              className="p-2 text-danger hover:text-danger"
              aria-label="Remove header"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6L6 18M6 6l12 12"></path>
              </svg>
            </button>
          </div>
        </div>
      ))}

      <div className="flex flex-wrap gap-2 mt-2">
        <button
          type="button"
          onClick={addHeader}
          className="text-sm text-info hover:text-info flex items-center"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mr-1">
            <path d="M12 5v14M5 12h14"></path>
          </svg>
          Add Header
        </button>
      </div>

      <div className="text-xs text-secondary mt-3 p-2 bg-surface rounded">
        <p className="font-medium mb-1">Start typing to see header name suggestions. After selecting a header, value suggestions will appear.</p>
      </div>
    </div>
  );
}
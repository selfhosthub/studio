// ui/features/step-config/sections/HttpServiceSection.tsx

'use client';

import React, { useState, useEffect } from 'react';
import HttpHeadersEditor from '../HttpHeadersEditor';
import { useSharedStepConfig } from '../context/SharedStepConfigContext';

interface HttpServiceSectionProps {
  title?: string;
}

const HttpServiceSection: React.FC<HttpServiceSectionProps> = ({
  title = 'Service Configuration'
}) => {
  const { serviceId, parameters, setParameters, service } = useSharedStepConfig();
  
  // Helper function to update a specific parameter
  const handleParameterChange = (key: string, value: any) => {
    setParameters({
      ...parameters,
      [key]: value
    });
  };
  
  const [bodyType, setBodyType] = useState<'json' | 'text'>(
    parameters?.body && typeof parameters.body === 'object' ? 'json' : 'text'
  );
  
  const [jsonError, setJsonError] = useState('');
  
  // Add default Content-Type header for HTTP POST on component mount
  // And apply example parameters if available and parameters aren't already set
  useEffect(() => {
    // Only run this effect when service or serviceId changes to avoid infinite loops
    const newParams: Record<string, any> = { ...parameters };
    let hasChanges = false;
    
    // Add default Content-Type header for POST requests
    if (serviceId === 'http-post' && bodyType === 'json') {
      const headers = parameters?.headers || {};
      if (!headers['Content-Type']) {
        newParams.headers = {
          ...headers,
          'Content-Type': 'application/json'
        };
        hasChanges = true;
      }
    }
    
    // Apply example parameters when the service is first loaded and parameters are not adequately set
    // Consider parameters not adequately set if:
    // 1. Empty parameters object
    // 2. Missing URL for HTTP requests
    // 3. Missing body for POST requests
    const isParametersEmpty = !parameters || Object.keys(parameters).length === 0;
    const isMissingUrl = parameters?.url === undefined || parameters?.url === '';
    const isMissingBody = serviceId === 'http-post' && (parameters?.body === undefined || 
                         (typeof parameters.body === 'object' && Object.keys(parameters.body).length === 0) ||
                         parameters.body === '');
    const isMissingHeaders = !parameters?.headers || Object.keys(parameters?.headers || {}).length === 0;
    
    if (service?.example_parameters && (isParametersEmpty || isMissingUrl || isMissingBody)) {
      // Apply example URL if available and not already set or empty
      if (service.example_parameters.url && isMissingUrl) {
        newParams.url = service.example_parameters.url;
        hasChanges = true;
      }
      
      // Apply example headers if available and not already set
      if (service.example_parameters.headers && isMissingHeaders) {
        newParams.headers = {
          ...newParams.headers,
          ...service.example_parameters.headers
        };
        hasChanges = true;
      }
      
      // Apply example body for POST requests if available and not already set or empty
      if (serviceId === 'http-post' && service.example_parameters.body && isMissingBody) {
        newParams.body = service.example_parameters.body;
        hasChanges = true;
      }
    }
    
    // Update parameters if any changes were made
    if (hasChanges) {
      setParameters(newParams);
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps -- parameters/bodyType excluded to prevent loop; effect sets parameters based on service defaults
  }, [serviceId, service, setParameters]);
  
  // Helper function to handle JSON changes
  const handleJsonBodyChange = (value: string) => {
    try {
      // Parse input as JSON to validate
      const jsonBody = JSON.parse(value);
      handleParameterChange('body', jsonBody);
      setJsonError('');
    } catch (error) {
      // If parsing fails, keep the raw value but show an error
      setJsonError('Invalid JSON: Please check your syntax');
    }
  };
  
  // Handle body type change
  const handleBodyTypeChange = (type: 'json' | 'text') => {
    setBodyType(type);
    
    // Convert existing body if needed
    if (type === 'json' && parameters?.body && typeof parameters.body === 'string') {
      try {
        const jsonBody = JSON.parse(parameters.body);
        handleParameterChange('body', jsonBody);
        
        // Add Content-Type application/json header if converting to JSON
        const headers = parameters?.headers || {};
        if (!headers['Content-Type']) {
          handleParameterChange('headers', {
            ...headers,
            'Content-Type': 'application/json'
          });
        }
        
        setJsonError('');
      } catch (error) {
        // If parsing fails, create an empty object
        handleParameterChange('body', {});
        setJsonError('');
      }
    } else if (type === 'text' && parameters?.body && typeof parameters.body === 'object') {
      // Convert object to JSON string
      handleParameterChange('body', JSON.stringify(parameters.body, null, 2));
    }
  };

  // State for test response
  const [testResponse, setTestResponse] = useState<any>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);

  // Function to test the API call
  const handleTestApiCall = async () => {
    // Reset previous test state
    setTestResponse(null);
    setTestError(null);
    setTestLoading(true);

    try {
      // Validate required fields
      if (!parameters.url) {
        throw new Error('URL is required for testing');
      }
      
      if (serviceId === 'http-post' && !parameters.body) {
        throw new Error('Body is required for POST requests');
      }

      const { apiRequest } = await import('@/shared/api');
      const result = await apiRequest('/providers/test-http-service', {
        method: 'POST',
        body: JSON.stringify({ serviceId, parameters }),
      });
      setTestResponse(result);
    } catch (error) {
      setTestError(error instanceof Error ? error.message : 'Unknown error occurred');
    } finally {
      setTestLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* URL */}
      <div>
        <label htmlFor="url" className="form-label">
          URL {serviceId === 'http-get' && <span className="text-danger">*</span>}
        </label>
        <input
          id="url"
          type="text"
          value={parameters?.url || ''}
          onChange={(e) => handleParameterChange('url', e.target.value)}
          className="form-input mt-1 block p-2"
          placeholder="https://api.example.com/endpoint"
        />
      </div>
      
      {/* HTTP Headers */}
      <div>
        <HttpHeadersEditor 
          headers={parameters?.headers || {}} 
          onChange={(headers) => handleParameterChange('headers', headers)} 
        />
      </div>
      
      {/* HTTP POST Body (only for POST requests) */}
      {serviceId === 'http-post' && (
        <div className="space-y-3">
          <div>
            <label className="form-label">
              Body {serviceId === 'http-post' && <span className="text-danger">*</span>}
            </label>
            
            {/* Toggle between JSON and Text formats */}
            <div className="flex space-x-4 mt-1 mb-2">
              <label className="flex items-center space-x-1">
                <input
                  type="radio"
                  checked={bodyType === 'json'}
                  onChange={() => handleBodyTypeChange('json')}
                  className="text-info"
                />
                <span className="text-sm">JSON</span>
              </label>
              <label className="flex items-center space-x-1">
                <input
                  type="radio"
                  checked={bodyType === 'text'}
                  onChange={() => handleBodyTypeChange('text')}
                  className="text-info"
                />
                <span className="text-sm">Text</span>
              </label>
            </div>
            
            {bodyType === 'json' ? (
              <>
                <textarea
                  rows={10}
                  value={parameters?.body && typeof parameters.body === 'object' 
                    ? JSON.stringify(parameters.body, null, 2) 
                    : '{}'}
                  onChange={(e) => handleJsonBodyChange(e.target.value)}
                  className="form-input block p-2 font-mono text-sm"
                  placeholder='{ "key": "value" }'
                />
                {jsonError && (
                  <p className="text-danger text-xs mt-1">{jsonError}</p>
                )}
              </>
            ) : (
              <textarea
                rows={5}
                value={parameters?.body && typeof parameters.body === 'string' 
                  ? parameters.body 
                  : parameters?.body 
                    ? JSON.stringify(parameters.body)
                    : ''}
                onChange={(e) => handleParameterChange('body', e.target.value)}
                className="form-input block p-2"
                placeholder="Request body (text)"
              />
            )}
          </div>
        </div>
      )}

      {/* Test API Call Button */}
      <div className="mt-4">
        <button
          type="button"
          onClick={handleTestApiCall}
          disabled={testLoading || !parameters.url}
          className={`px-4 py-2 rounded-md text-white ${
            testLoading || !parameters.url
              ? 'bg-muted cursor-not-allowed'
              : 'bg-info hover:opacity-90'
          }`}
        >
          {testLoading ? 'Testing...' : 'Test API Call'}
        </button>
      </div>

      {/* Test Results */}
      {testError && (
        <div className="mt-4 p-3 bg-danger-subtle border border-danger rounded-md">
          <h4 className="text-sm font-medium text-danger">Error</h4>
          <p className="text-sm text-danger mt-1">{testError}</p>
        </div>
      )}

      {testResponse && (
        <div className="mt-4 p-3 bg-success-subtle border border-success rounded-md">
          <h4 className="text-sm font-medium text-success">Test Response</h4>
          <pre className="mt-2 p-2 bg-card border border-success rounded-md text-xs overflow-auto max-h-64">
            {JSON.stringify(testResponse, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

export default HttpServiceSection;
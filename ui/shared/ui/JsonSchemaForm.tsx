// ui/shared/ui/JsonSchemaForm.tsx

import React, { useState, useEffect, useMemo } from 'react';
import { ParameterSchema, PropertySchema } from '@/shared/types/schema';
import DynamicCombobox from './DynamicCombobox';

const EMPTY_OBJECT: Record<string, any> = {};

interface JsonSchemaFormProps {
  schema: ParameterSchema;
  initialData?: Record<string, any>;
  exampleParameters?: Record<string, any>;
  onChange: (data: Record<string, any>) => void;
  className?: string;
  providerId?: string;
  credentialId?: string;
}

export default function JsonSchemaForm({
  schema,
  initialData = EMPTY_OBJECT,
  exampleParameters = EMPTY_OBJECT,
  onChange,
  className = '',
  providerId,
  credentialId,
}: JsonSchemaFormProps) {
  const [formData, setFormData] = useState<Record<string, any>>(initialData);
  
  // Merge priority: initialData → exampleParameters (skip dynamicOptions fields) → schema defaults.
  useEffect(() => {
    if (schema?.properties) {
      const combinedData: Record<string, any> = {};

      Object.entries(schema.properties).forEach(([key, prop]: [string, any]) => {
        if (formData[key] !== undefined) {
          combinedData[key] = formData[key];
        } else if (exampleParameters[key] !== undefined && !prop.dynamicOptions) {
          combinedData[key] = exampleParameters[key];
        } else if (prop.default !== undefined) {
          combinedData[key] = prop.default;
        }
      });

      if (Object.keys(combinedData).length > 0) {
        const newData = { ...formData, ...combinedData };
        setFormData(newData);
        onChange(newData);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- formData/onChange excluded to avoid infinite loops
  }, [schema, exampleParameters]);
  
  const handleChange = (key: string, value: any) => {
    const newData = { ...formData, [key]: value };
    setFormData(newData);
    onChange(newData);
  };
  
  const renderField = (key: string, property: PropertySchema) => {
    const isRequired = schema.required?.includes(key) || false;
    const value = formData[key] !== undefined ? formData[key] : property.default;
    
    switch (property.type) {
      case 'string':
        return renderStringField(key, property, value, isRequired);
        
      case 'number':
      case 'integer':
        return renderNumberField(key, property, value, isRequired);
        
      case 'boolean':
        return renderBooleanField(key, property, value, isRequired);
        
      case 'array':
        return renderArrayField(key, property, value, isRequired);
        
      case 'object':
        return renderObjectField(key, property, value, isRequired);
        
      default:
        return (
          <div key={key} className="mb-4">
            <label className="block mb-1">
              {property.title || key} (Unsupported type: {property.type})
            </label>
            {property.description && (
              <p className="text-sm text-secondary mb-1">{property.description}</p>
            )}
          </div>
        );
    }
  };
  
  const renderStringField = (key: string, property: PropertySchema, value: string, isRequired: boolean) => {
    if (property.dynamicOptions && providerId) {
      const exampleValue = exampleParameters[key];
      const placeholderText = exampleValue
        ? `e.g. ${exampleValue}`
        : property.placeholder || `Select or enter ${property.title || key}...`;

      return (
        <div key={key} className="mb-4">
          <label htmlFor={key} className="block mb-1">
            {property.title || key} {isRequired && <span className="text-danger">*</span>}
          </label>
          {property.description && (
            <p className="text-sm text-secondary mb-1">{property.description}</p>
          )}
          <DynamicCombobox
            id={key}
            value={value || ''}
            onChange={(newValue) => handleChange(key, newValue)}
            dynamicOptions={property.dynamicOptions}
            providerId={providerId}
            credentialId={credentialId}
            formData={formData}
            required={isRequired}
            placeholder={placeholderText}
          />
        </div>
      );
    }

    if (property.enum) {
      return (
        <div key={key} className="mb-4">
          <label htmlFor={key} className="block mb-1">
            {property.title || key} {isRequired && <span className="text-danger">*</span>}
          </label>
          {property.description && (
            <p className="text-sm text-secondary mb-1">{property.description}</p>
          )}
          <select
            id={key}
            value={value || ''}
            onChange={(e) => handleChange(key, e.target.value)}
            className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            required={isRequired}
          >
            <option value="">Select an option</option>
            {property.enum?.map((option: string) => (
              <option key={option} value={option}>
                {property.enumNames?.[property.enum?.indexOf(option) || 0] || option}
              </option>
            ))}
          </select>
        </div>
      );
    } else if (property.format === 'textarea' || property.multiline) {
      return (
        <div key={key} className="mb-4">
          <label htmlFor={key} className="block mb-1">
            {property.title || key} {isRequired && <span className="text-danger">*</span>}
          </label>
          {property.description && (
            <p className="text-sm text-secondary mb-1">{property.description}</p>
          )}
          <textarea
            id={key}
            value={value || ''}
            onChange={(e) => handleChange(key, e.target.value)}
            className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={property.rows || 4}
            required={isRequired}
            placeholder={property.placeholder || ''}
          />
        </div>
      );
    } else {
      return (
        <div key={key} className="mb-4">
          <label htmlFor={key} className="block mb-1">
            {property.title || key} {isRequired && <span className="text-danger">*</span>}
          </label>
          {property.description && (
            <p className="text-sm text-secondary mb-1">{property.description}</p>
          )}
          <input
            id={key}
            type={property.format === 'password' ? 'password' : 'text'}
            value={value || ''}
            onChange={(e) => handleChange(key, e.target.value)}
            className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            required={isRequired}
            placeholder={property.placeholder || ''}
            pattern={property.pattern}
            minLength={property.minLength}
            maxLength={property.maxLength}
          />
        </div>
      );
    }
  };
  
  const renderNumberField = (key: string, property: PropertySchema, value: number | undefined, isRequired: boolean) => {
    return (
      <div key={key} className="mb-4">
        <label htmlFor={key} className="block mb-1">
          {property.title || key} {isRequired && <span className="text-danger">*</span>}
        </label>
        {property.description && (
          <p className="text-sm text-secondary mb-1">{property.description}</p>
        )}
        <input
          id={key}
          type="number"
          value={value !== undefined ? value : ''}
          onChange={(e) => {
            const val = e.target.value === '' ? undefined : 
              property.type === 'integer' ? 
                parseInt(e.target.value, 10) : 
                parseFloat(e.target.value);
            handleChange(key, val);
          }}
          className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          required={isRequired}
          min={property.minimum}
          max={property.maximum}
          step={property.type === 'integer' ? 1 : 'any'}
        />
      </div>
    );
  };
  
  const renderBooleanField = (key: string, property: PropertySchema, value: boolean, isRequired: boolean) => {
    return (
      <div key={key} className="mb-4">
        <div className="flex items-center">
          <input
            id={key}
            type="checkbox"
            checked={!!value}
            onChange={(e) => handleChange(key, e.target.checked)}
            className="mr-2 h-4 w-4"
            required={isRequired}
          />
          <label htmlFor={key} className="cursor-pointer">
            {property.title || key} {isRequired && <span className="text-danger">*</span>}
          </label>
        </div>
        {property.description && (
          <p className="text-sm text-secondary ml-6">{property.description}</p>
        )}
      </div>
    );
  };
  
  const renderArrayField = (key: string, property: PropertySchema, value: any[] = [], isRequired: boolean) => {
    const arrayValue = Array.isArray(value) ? value : [];
    
    return (
      <div key={key} className="mb-4">
        <label className="block mb-1">
          {property.title || key} {isRequired && <span className="text-danger">*</span>}
        </label>
        {property.description && (
          <p className="text-sm text-secondary mb-1">{property.description}</p>
        )}
        
        <div className="border rounded p-3">
          {arrayValue.map((item, index) => (
            <div key={index} className="flex mb-2">
              <input
                type="text"
                value={item || ''}
                onChange={(e) => {
                  const newArray = [...arrayValue];
                  newArray[index] = e.target.value;
                  handleChange(key, newArray);
                }}
                className="flex-grow p-2 border rounded mr-2"
              />
              <button
                type="button"
                onClick={() => {
                  const newArray = arrayValue.filter((_, i) => i !== index);
                  handleChange(key, newArray);
                }}
                className="px-3 py-1 bg-red-500 text-white rounded"
              >
                Remove
              </button>
            </div>
          ))}
          
          <button
            type="button"
            onClick={() => {
              handleChange(key, [...arrayValue, '']);
            }}
            className="flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium text-info hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-md border border-dashed border-blue-400 dark:border-blue-600 w-full justify-center mt-2 transition-colors"
          >
            Add Item
          </button>
        </div>
      </div>
    );
  };
  
  const renderObjectField = (key: string, property: PropertySchema, value: Record<string, any> = {}, isRequired: boolean) => {
    if (!property.properties) {
      return (
        <div key={key} className="mb-4">
          <label className="block mb-1">
            {property.title || key} (Object without properties)
          </label>
        </div>
      );
    }
    
    return (
      <div key={key} className="mb-4">
        <fieldset className="border rounded p-3">
          <legend className="px-2">
            {property.title || key} {isRequired && <span className="text-danger">*</span>}
          </legend>
          
          {property.description && (
            <p className="text-sm text-secondary mb-3">{property.description}</p>
          )}
          
          {property.properties && Object.entries(property.properties).map(([propKey, propSchema]: [string, PropertySchema]) => {
            const fieldValue = value?.[propKey];
            const fieldIsRequired = property.required?.includes(propKey) || false;

            switch (propSchema.type) {
              case 'string':
                return renderStringField(`${key}.${propKey}`, propSchema, fieldValue, fieldIsRequired);
              case 'number':
              case 'integer':
                return renderNumberField(`${key}.${propKey}`, propSchema, fieldValue, fieldIsRequired);
              case 'boolean':
                return renderBooleanField(`${key}.${propKey}`, propSchema, fieldValue, fieldIsRequired);
              default:
                return (
                  <div key={propKey} className="mb-2">
                    <label className="block">{propSchema.title || propKey}</label>
                    <input
                      type="text"
                      value={fieldValue || ''}
                      onChange={(e) => {
                        const newObj = { ...value };
                        newObj[propKey] = e.target.value;
                        handleChange(key, newObj);
                      }}
                      className="w-full p-2 border rounded"
                    />
                  </div>
                );
            }
          })}
        </fieldset>
      </div>
    );
  };
  
  if (!schema || !schema.properties) {
    return <div className="p-4 border border-danger bg-red-50 rounded">Invalid schema: no properties defined</div>;
  }
  
  return (
    <div className={`json-schema-form${className}`}>
      {Object.entries(schema.properties).map(([key, property]: [string, PropertySchema]) => 
        renderField(key, property)
      )}
    </div>
  );
}
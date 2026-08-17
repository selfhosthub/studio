// ui/app/(authenticated)/comfyui/upload/page.tsx

"use client";

import React, { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useUser } from '@/entities/user';
import { uploadComfyUIPackage } from '@/shared/api/comfyui';

export default function UploadComfyUIPackagePage() {
  const router = useRouter();
  const { user } = useUser();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const isSuperAdmin = user?.role === 'super_admin';
  if (!isSuperAdmin) {
    return (
      <>
        <div className="px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-primary">Access Denied</h2>
            <p className="mt-2 text-muted">ComfyUI workflow upload is only available to super admins.</p>
          </div>
        </div>
      </>
    );
  }

  const handleFileSelect = (file: File) => {
    if (!file.name.endsWith('.json')) {
      setError('Please select a .json file');
      return;
    }
    setSelectedFile(file);
    setError(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setError('Please select a workflow file');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await uploadComfyUIPackage(selectedFile);
      if (result.success) {
        router.push('/comfyui/marketplace?tab=custom');
      } else {
        setError(result.message || 'Failed to upload workflow'); // defaults-ok
        setLoading(false);
      }
    } catch (err: unknown) {
      console.error('Failed to upload ComfyUI package:', err);
      setError(err instanceof Error ? err.message : 'Failed to upload workflow');
      setLoading(false);
    }
  };

  return (
    <>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-3xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-primary">
            Upload ComfyUI Workflow
          </h1>
          <p className="text-sm mt-1 text-secondary">
            Install a ComfyUI workflow from a single JSON file
          </p>
        </div>

        {error && (
          <div className="mb-6 bg-danger-subtle border border-danger rounded-md p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-danger" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-danger">{error}</p>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="bg-card shadow rounded-lg p-6 border border-primary">
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              dragActive
                ? 'border-info bg-info-subtle'
                : selectedFile
                ? 'border-success bg-success-subtle'
                : 'border-primary hover:border-secondary'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              onChange={handleFileChange}
              className="hidden"
            />

            {selectedFile ? (
              <div>
                <svg className="mx-auto h-12 w-12 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="mt-2 text-sm font-medium text-primary">
                  {selectedFile.name}
                </p>
                <p className="mt-1 text-xs text-secondary">
                  {(selectedFile.size / 1024).toFixed(1)} KB
                </p>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                  }}
                  className="mt-2 text-sm text-danger hover:text-danger"
                >
                  Remove
                </button>
              </div>
            ) : (
              <div>
                <svg className="mx-auto h-12 w-12 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="mt-2 text-sm font-medium text-primary">
                  Drop your workflow file here, or click to browse
                </p>
                <p className="mt-1 text-xs text-secondary">
                  JSON files only
                </p>
              </div>
            )}
          </div>

          <div className="mt-6 bg-surface rounded-lg p-4">
            <h3 className="text-sm font-medium text-primary mb-2">
              Required fields
            </h3>
            <ul className="text-xs text-secondary space-y-1">
              <li className="flex items-center gap-2">
                <svg className="h-4 w-4 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4" />
                </svg>
                <code className="bg-card px-1 rounded">slug</code>, <code className="bg-card px-1 rounded">version</code>, <code className="bg-card px-1 rounded">name</code>
              </li>
              <li className="flex items-center gap-2">
                <svg className="h-4 w-4 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4" />
                </svg>
                <code className="bg-card px-1 rounded">description</code>, <code className="bg-card px-1 rounded">author</code>, <code className="bg-card px-1 rounded">graph</code>
              </li>
            </ul>
          </div>

          <div className="mt-8 flex items-center justify-end space-x-4">
            <button
              type="button"
              onClick={() => router.back()}
              disabled={loading}
              className="btn-danger"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !selectedFile}
              className="btn-primary"
            >
              {loading ? 'Uploading...' : 'Upload Workflow'}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

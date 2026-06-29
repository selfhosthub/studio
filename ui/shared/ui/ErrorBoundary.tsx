// ui/shared/ui/ErrorBoundary.tsx

'use client';

import React, { Component } from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Name shown in the fallback UI (e.g. "Flow Editor") */
  name?: string;
  /** Optional custom fallback renderer */
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error(`[ErrorBoundary${this.props.name ? `: ${this.props.name}` : ''}]`, error, errorInfo); // nosemgrep: unsafe-formatstring
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): React.ReactNode {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.handleReset);
      }

      return (
        <div className="flex items-center justify-center p-8" role="alert" aria-live="assertive">
          <div className="text-center max-w-sm">
            <p className="text-lg font-semibold text-primary mb-2">
              {this.props.name ? `${this.props.name} failed to load` : 'Something went wrong'}
            </p>
            <p className="text-sm text-muted mb-4">
              An unexpected error occurred. Try again or reload the page.
            </p>
            <button
              onClick={this.handleReset}
              className="action-btn action-btn-active"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

// ui/widgets/instance-view/index.tsx

import React from 'react';
import { ErrorBoundary } from '@/shared/ui';

// Main instance view component
import InstanceSimpleViewInner from './InstanceSimpleView';
export type { InstanceSimpleViewProps, Job, WorkflowStep, SelectedItem } from './InstanceSimpleView';

/** InstanceSimpleView wrapped with an error boundary */
export const InstanceSimpleView = (props: React.ComponentProps<typeof InstanceSimpleViewInner>) => (
  <ErrorBoundary name="Instance View">
    <InstanceSimpleViewInner {...props} />
  </ErrorBoundary>
);

// Supporting components
export { default as MediaViewerModal } from './MediaViewerModal';
export { default as ResourceCard, type CardSize } from './ResourceCard';
export { default as SortableResourceCard, SortableResourceCard as SortableResourceCardNamed } from './SortableResourceCard';

// Step config
export { default as InstanceStepConfig } from './step-config/InstanceStepConfig';

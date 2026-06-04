// ui/app/demo/flow-editor/page.tsx

'use client';

import { useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { Step } from '@/entities/workflow';
import type { FlexibleConnection } from '@/widgets/flow-editor';
import { FlowEditorWithProvider } from '@/widgets/flow-editor';

// Demo step data showing fan-out / fan-in pattern
const initialSteps: Step[] = [
  {
    id: 'step1',
    name: 'Process Request',
    description: 'Start the workflow',
    type: 'trigger',
  },
  {
    id: 'step2',
    name: 'Analyze Data',
    description: 'Process input data',
    type: 'task',
    depends_on: ['step1'],
  },
  {
    id: 'step3',
    name: 'Generate Report',
    description: 'Create output report',
    type: 'task',
    depends_on: ['step1'],
  },
  {
    id: 'step4',
    name: 'Final Processing',
    description: 'Combine results',
    type: 'task',
    depends_on: ['step2', 'step3'],
  }
];

// Demo connection data based on depends_on
const initialConnections: FlexibleConnection[] = [
  {
    id: 'conn-step1-step2',
    source_id: 'step1',
    target_id: 'step2',
  },
  {
    id: 'conn-step1-step3',
    source_id: 'step1',
    target_id: 'step3',
  },
  {
    id: 'conn-step2-step4',
    source_id: 'step2',
    target_id: 'step4',
  },
  {
    id: 'conn-step3-step4',
    source_id: 'step3',
    target_id: 'step4',
  }
];

export default function FlowEditorDemo() {
  const [steps, setSteps] = useState<Step[]>(initialSteps);
  const [connections, setConnections] = useState<FlexibleConnection[]>(initialConnections);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);

  // Update steps
  const handleStepsChange = (newSteps: Step[]) => {
    setSteps(newSteps);
  };

  // Update connections and sync depends_on
  const handleConnectionsChange = (newConnections: FlexibleConnection[]) => {
    setConnections(newConnections);
    
    // Update depends_on in steps based on connections
    const updatedSteps = steps.map(step => {
      const incomingConnections = newConnections.filter(conn => conn.target_id === step.id);
      const depends_on = incomingConnections.map(conn => conn.source_id);
      
      return {
        ...step,
        depends_on: depends_on.length > 0 ? depends_on.filter((id): id is string => id !== undefined) : undefined,
      };
    });
    
    setSteps(updatedSteps);
  };

  // Add a new step
  const addStep = () => {
    const newStep: Step = {
      id: `step-${uuidv4().slice(0, 8)}`,
      name: `New Step`,
      description: `Step description`,
      type: 'task',
    };
    
    setSteps([...steps, newStep]);
  };

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Flow Editor Demo</h1>
      <p className="mb-4 text-secondary">
        This demonstrates the dependency-based workflow connections using React Flow.
      </p>
      
      <div className="mb-4">
        <button 
          onClick={addStep}
          className="btn-primary"
        >
          Add Step
        </button>
      </div>
      
      <div className="bg-card p-4 rounded-lg shadow-md">
        <FlowEditorWithProvider 
          steps={steps}
          connections={connections}
          onStepsChange={handleStepsChange}
          onConnectionsChange={handleConnectionsChange}
          onStepSelect={setSelectedStepId}
          selectedStepId={selectedStepId}
        />
      </div>
      
      <div className="mt-4 bg-card p-4 rounded-lg shadow-md">
        <h2 className="text-lg font-semibold mb-2">Instructions</h2>
        <ul className="list-disc list-inside space-y-1 text-sm text-secondary">
          <li>Drag nodes to reposition them</li>
          <li>Drag from the right handle of a node to the left handle of another node to create connections</li>
          <li>Connections automatically update the depends_on property in the data model</li>
        </ul>
      </div>
    </div>
  );
}
// ui/app/demo/flow-editor-basic/page.tsx

'use client';

export default function BasicFlowEditorPage() {
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Workflow Visualization Demo</h1>
      
      <div className="bg-card p-4 rounded-lg shadow-md mb-4">
        <h2 className="text-lg font-semibold mb-2">Workflow Diagram</h2>
        <div className="border border-primary p-4 rounded-md">
          <svg 
            width="800" 
            height="400" 
            viewBox="0 0 800 400" 
            xmlns="http://www.w3.org/2000/svg"
            className="mx-auto"
          >
            {/* Step 1: Process Request */}
            <rect x="50" y="150" width="150" height="80" rx="5" fill="#f0f9ff" stroke="#3b82f6" strokeWidth="2"/>
            <text x="125" y="180" textAnchor="middle" fontFamily="sans-serif" fontSize="14" fontWeight="bold">Process Request</text>
            <text x="125" y="200" textAnchor="middle" fontFamily="sans-serif" fontSize="12" fill="#4b5563">Step 1</text>
            
            {/* Step 2: Analyze Data */}
            <rect x="325" y="50" width="150" height="80" rx="5" fill="#f0f9ff" stroke="#3b82f6" strokeWidth="2"/>
            <text x="400" y="80" textAnchor="middle" fontFamily="sans-serif" fontSize="14" fontWeight="bold">Analyze Data</text>
            <text x="400" y="100" textAnchor="middle" fontFamily="sans-serif" fontSize="12" fill="#4b5563">Step 2</text>
            
            {/* Step 3: Generate Report */}
            <rect x="325" y="250" width="150" height="80" rx="5" fill="#f0f9ff" stroke="#3b82f6" strokeWidth="2"/>
            <text x="400" y="280" textAnchor="middle" fontFamily="sans-serif" fontSize="14" fontWeight="bold">Generate Report</text>
            <text x="400" y="300" textAnchor="middle" fontFamily="sans-serif" fontSize="12" fill="#4b5563">Step 3</text>
            
            {/* Step 4: Final Processing */}
            <rect x="600" y="150" width="150" height="80" rx="5" fill="#f0f9ff" stroke="#3b82f6" strokeWidth="2"/>
            <text x="675" y="180" textAnchor="middle" fontFamily="sans-serif" fontSize="14" fontWeight="bold">Final Processing</text>
            <text x="675" y="200" textAnchor="middle" fontFamily="sans-serif" fontSize="12" fill="#4b5563">Step 4</text>
            
            {/* Arrow 1 to 2 */}
            <path d="M 200 170 C 250 170, 250 90, 325 90" stroke="#3b82f6" strokeWidth="2" fill="none" markerEnd="url(#arrowhead)"/>
            
            {/* Arrow 1 to 3 */}
            <path d="M 200 190 C 250 190, 250 290, 325 290" stroke="#3b82f6" strokeWidth="2" fill="none" markerEnd="url(#arrowhead)"/>
            
            {/* Arrow 2 to 4 */}
            <path d="M 475 90 C 525 90, 525 170, 600 170" stroke="#3b82f6" strokeWidth="2" fill="none" markerEnd="url(#arrowhead)"/>
            
            {/* Arrow 3 to 4 */}
            <path d="M 475 290 C 525 290, 525 190, 600 190" stroke="#3b82f6" strokeWidth="2" fill="none" markerEnd="url(#arrowhead)"/>
            
            {/* Arrowhead marker definition */}
            <defs>
              <marker
                id="arrowhead"
                markerWidth="10"
                markerHeight="7"
                refX="9"
                refY="3.5"
                orient="auto"
              >
                <polygon points="0 0, 10 3.5, 0 7" fill="#3b82f6" />
              </marker>
            </defs>
          </svg>
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card p-4 rounded-lg shadow-md">
          <h2 className="text-lg font-semibold mb-2">Pattern Example</h2>
          <p className="text-secondary mb-3">
            This diagram shows two important workflow patterns:
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-secondary mb-3">
            <li><strong>Fan-out:</strong> One step (Process Request) branches to multiple parallel steps</li>
            <li><strong>Fan-in:</strong> Multiple parallel steps converge to a single step (Final Processing)</li>
          </ul>
          <p className="text-secondary">
            These patterns are commonly used in workflow design to allow for parallel processing and then 
            aggregation of results.
          </p>
        </div>
        
        <div className="bg-card p-4 rounded-lg shadow-md">
          <h2 className="text-lg font-semibold mb-2">Workflow Components</h2>
          <div className="space-y-3">
            <div className="flex items-center space-x-3 p-2 border border-primary rounded-md">
              <div className="w-8 h-8 bg-info-subtle rounded-md flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-info" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div>
                <div className="font-medium">Trigger Steps</div>
                <div className="text-xs text-secondary">Start a workflow execution</div>
              </div>
            </div>
            
            <div className="flex items-center space-x-3 p-2 border border-primary rounded-md">
              <div className="w-8 h-8 bg-success-subtle rounded-md flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </div>
              <div>
                <div className="font-medium">Action Steps</div>
                <div className="text-xs text-secondary">Perform operations on data</div>
              </div>
            </div>
            
            <div className="flex items-center space-x-3 p-2 border border-primary rounded-md">
              <div className="w-8 h-8 bg-orange-100 rounded-md flex items-center justify-center"> {/* css-check-ignore: no semantic token */}
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-orange-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"> {/* css-check-ignore: no semantic token */}
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <div className="font-medium">Decision Steps</div>
                <div className="text-xs text-secondary">Conditionally route workflow</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
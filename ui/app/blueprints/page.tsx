// ui/app/blueprints/page.tsx

'use client';

import { notFound } from 'next/navigation';
import { ListPageLayout } from '@/widgets/layout';
import { usePageVisibility } from '@/entities/page-visibility';
import { useUser } from '@/entities/user';
import {
  MessageSquare,
  FileCode2,
  History,
  Store,
  Shield,
  Plug,
  ChevronRight,
} from 'lucide-react';

const visionFeatures = [
  {
    icon: MessageSquare,
    title: 'Conversational Canvas',
    description:
      'Open a blank canvas and describe what you want to automate. AI structures your intent into a blueprint as you talk - no forms, no drag-and-drop.',
  },
  {
    icon: FileCode2,
    title: 'Intent, Not Configuration',
    description:
      'Blueprints capture what you want to happen, not how. Hit Go and the system resolves your intent against available tools - deterministic, no AI tokens burned.',
  },
  {
    icon: Shield,
    title: 'Best of Both Worlds',
    description:
      'AI handles the fuzzy work upfront - understanding your intent and structuring it into a plan. From there, execution is deterministic. No AI improvising at runtime, no runaway costs.',
  },
  {
    icon: History,
    title: 'Conversation as Artifact',
    description:
      'The AI dialogue that built your blueprint is stored alongside it. Edit, fork, or pick up exactly where you left off with full context.',
  },
  {
    icon: Plug,
    title: 'Your Tools, Your Rules',
    description:
      'Studio resolves blueprints against your connected MCP servers and tools - not a hardcoded vendor list. Swap providers without rewriting automations.',
  },
  {
    icon: Store,
    title: 'Marketplace Shares Intent',
    description:
      'Install a blueprint and get a workflow tailored to your infrastructure. Same intent, different execution - every time.',
  },
];

const steps = [
  {
    number: '1',
    label: 'Describe',
    detail: 'Talk to AI about what you want to automate',
  },
  {
    number: '2',
    label: 'Compile',
    detail: 'System resolves intent against your available tools',
  },
  {
    number: '3',
    label: 'Run',
    detail: 'Execute as a concrete workflow, ready to trigger',
  },
];

export default function BlueprintsVisionPage() {
  const { user } = useUser();
  const { visibility, isLoading } = usePageVisibility();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="spinner-md"></div>
      </div>
    );
  }

  // Super-admins always see the vision page; others only when enabled
  if (user?.role !== 'super_admin' && !visibility.blueprints) {
    notFound();
  }

  return (
    <ListPageLayout
      title="Blueprints"
      description="Intent-based workflow automation"
    >
      {/* Coming Soon Badge + Hero */}
      <div className="text-center mb-12">
        <span className="inline-block px-3 py-1 text-xs font-semibold text-info bg-info-subtle rounded-full mb-4">
          Coming Soon
        </span>
        <h2 className="text-3xl font-bold text-primary mb-4">
          The Future of Workflow Automation
        </h2>
        <p className="text-secondary max-w-2xl mx-auto text-base leading-relaxed">
          We are reimagining blueprints as a conversational, AI-native experience.
          Describe what you want to accomplish. Studio figures out the rest.
        </p>
      </div>

      {/* Vision Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
        {visionFeatures.map((feature) => (
          <div
            key={feature.title}
            className="bg-card border border-primary rounded-lg p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 rounded-md bg-info-subtle">
                <feature.icon size={20} className="text-info" />
              </div>
              <h3 className="font-semibold text-primary">{feature.title}</h3>
            </div>
            <p className="text-secondary text-sm leading-relaxed">
              {feature.description}
            </p>
          </div>
        ))}
      </div>

      {/* How It Works */}
      <div className="bg-surface border border-primary rounded-lg p-8">
        <h3 className="text-lg font-semibold text-primary text-center mb-6">
          How It Works
        </h3>
        <div className="flex flex-col md:flex-row items-center justify-center gap-4">
          {steps.map((step, i) => (
            <div key={step.label} className="flex items-center gap-4">
              <div className="text-center min-w-[180px]">
                <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-info-subtle text-info font-bold mb-2">
                  {step.number}
                </div>
                <p className="font-semibold text-primary">{step.label}</p>
                <p className="text-muted text-sm">{step.detail}</p>
              </div>
              {i < steps.length - 1 && (
                <ChevronRight
                  size={20}
                  className="text-muted hidden md:block flex-shrink-0"
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Footer Note */}
      <p className="text-center text-muted text-sm mt-8">
        The blueprint engine is being rebuilt from the ground up.
        Workflows remain fully available for building and running automations today.
      </p>
    </ListPageLayout>
  );
}

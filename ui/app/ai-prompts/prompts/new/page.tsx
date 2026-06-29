// ui/app/ai-prompts/prompts/new/page.tsx

"use client";

import { Suspense } from "react";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useToast } from "@/features/toast";
import { createPrompt } from "@/shared/api";
import { useUser } from "@/entities/user";
import { useReturnTo } from "@/shared/hooks/useReturnTo";
import PromptForm, {
  type PromptFormData,
} from "../components/PromptForm";

export default function NewPromptPage() {
  return (
    <Suspense>
      <NewPromptPageContent />
    </Suspense>
  );
}

function NewPromptPageContent() {
  const { toast } = useToast();
  const { user } = useUser();
  const isSuperAdmin = user?.role === "super_admin";
  // Fall back to the tab a fresh prompt lands in when there's no referrer.
  const { returnTo, goBack } = useReturnTo(
    `/ai-prompts/prompts/list?tab=${isSuperAdmin ? "custom" : "my-prompts"}`
  );

  const handleSubmit = async (data: PromptFormData) => {
    // Role→scope rule (mirrors workflows): super_admin authors org-level
    // content directly; everyone else creates personal content needing approval.
    const scope = isSuperAdmin ? "organization" : "personal";
    await createPrompt({ ...data, scope });
    toast({ title: "Prompt created", variant: "success" });
    goBack();
  };

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-3xl mx-auto">
      <Link
        href={returnTo}
        className="link-subtle inline-flex items-center mb-4"
      >
        <ArrowLeft size={16} className="mr-1" />
        Back to Prompts
      </Link>

      <h1 className="text-2xl font-bold text-primary mb-6">
        New Prompt
      </h1>

      <PromptForm onSubmit={handleSubmit} submitLabel="Create Prompt" />
    </div>
  );
}

// ui/app/ai-agents/prompts/new/page.tsx

"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useToast } from "@/features/toast";
import { createPrompt } from "@/shared/api";
import PromptForm, {
  type PromptFormData,
} from "../components/PromptForm";

export default function NewPromptPage() {
  const router = useRouter();
  const { toast } = useToast();

  const handleSubmit = async (data: PromptFormData) => {
    await createPrompt(data);
    toast({ title: "Prompt created", variant: "success" });
    router.push("/ai-agents/prompts/list?tab=organization");
  };

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-3xl mx-auto">
      <Link
        href="/ai-agents/prompts/list"
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

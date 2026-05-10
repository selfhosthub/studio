// ui/app/ai-agents/prompts/[id]/edit/page.tsx

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useUser } from "@/entities/user";
import { useToast } from "@/features/toast";
import { getPrompt, updatePrompt } from "@/shared/api";
import { LoadingState, ErrorState } from "@/shared/ui";
import type { Prompt } from "@/shared/types/prompt";
import PromptForm, {
  type PromptFormData,
} from "../../components/PromptForm";

export default function EditPromptPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useUser();
  const { toast } = useToast();

  const promptId = params.id as string;

  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";

  useEffect(() => {
    if (!promptId) return;

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    getPrompt(promptId)
      .then((data) => {
        setPrompt(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || "Failed to load prompt");
      })
      .finally(() => setLoading(false));
  }, [promptId]);

  const handleSubmit = async (data: PromptFormData) => {
    await updatePrompt(promptId, data);
    toast({ title: "Prompt updated", variant: "success" });
    router.push("/ai-agents/prompts/list");
  };

  if (loading) {
    return (
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-3xl mx-auto">
        <LoadingState message="Loading prompt..." />
      </div>
    );
  }

  if (error || !prompt) {
    return (
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-3xl mx-auto">
        <ErrorState
          title="Error"
          message={error || "Prompt not found"}
          onRetry={() => window.location.reload()}
        />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-3xl mx-auto">
        <Link
          href="/ai-agents/prompts/list"
          className="link-subtle inline-flex items-center mb-4"
        >
          <ArrowLeft size={16} className="mr-1" />
          Back to My Prompts
        </Link>

        <h1 className="text-2xl font-bold text-primary mb-6">
          {prompt.name}
        </h1>

        <p className="text-secondary">
          You do not have permission to edit prompts. Contact an admin.
        </p>
      </div>
    );
  }

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-3xl mx-auto">
      <Link
        href="/ai-agents/prompts/list"
        className="link-subtle inline-flex items-center mb-4"
      >
        <ArrowLeft size={16} className="mr-1" />
        Back to My Prompts
      </Link>

      <h1 className="text-2xl font-bold text-primary mb-6">
        Edit: {prompt.name}
      </h1>

      <PromptForm
        initialData={{
          name: prompt.name,
          description: prompt.description || "",
          category: prompt.category,
          chunks: prompt.chunks,
          variables: prompt.variables,
        }}
        onSubmit={handleSubmit}
        submitLabel="Save Changes"
      />
    </div>
  );
}

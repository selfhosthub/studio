// ui/app/(authenticated)/ai-prompts/prompts/list/page.tsx

"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ListPageLayout } from "@/widgets/layout";
import { useUser } from "@/entities/user";
import { useToast } from "@/features/toast";
import {
  getPrompts,
  getPersonalPrompts,
  getPendingPublishPrompts,
  deletePrompt,
  copyPrompt,
  requestPublishPrompt,
  approvePublishPrompt,
  rejectPublishPrompt,
  setPromptVisibility,
} from "@/shared/api";
import type { Prompt } from "@/shared/types/prompt";
import { getStoredPageSize } from "@/shared/lib/pagination";
import { withReturnTo } from "@/shared/hooks/useReturnTo";
import { Plus, Upload } from "lucide-react";
import { PromptsOrganizationTab } from "./components/PromptsOrganizationTab";
import { PromptsMarketplaceTab } from "./components/PromptsMarketplaceTab";
import { PromptsMyTab } from "./components/PromptsMyTab";

const ORG_PAGE_SIZE_KEY = "prompt-templates-pageSize";
const MY_PAGE_SIZE_KEY = "my-prompts-pageSize";

type ActiveTab = "my-prompts" | "organization" | "custom" | "marketplace";

export default function PromptsListPage() {
  return (
    <Suspense>
      <PromptsListPageContent />
    </Suspense>
  );
}

function PromptsListPageContent() {
  const searchParams = useSearchParams();
  const { user, status: authStatus } = useUser();
  const { toast } = useToast();

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  const isSuperAdmin = user?.role === "super_admin";

  // ----------- Tab state (controlled locally; URL is for shareability only) -----------
  // useSearchParams() isn't reactive across App Router soft navigation, so deriving
  // activeTab from it leaves tab clicks dead until a hard refresh. Own the state here
  // and mirror it to the URL with replaceState.
  const defaultTab: ActiveTab = isSuperAdmin ? "marketplace" : "organization";
  const allowedTabs = useMemo<ActiveTab[]>(
    () =>
      isSuperAdmin
        ? ["custom", "marketplace"]
        : isAdmin
          ? ["my-prompts", "organization", "marketplace"]
          : ["my-prompts", "organization"],
    [isSuperAdmin, isAdmin]
  );

  const [activeTab, setActiveTab] = useState<ActiveTab | null>(null);

  // Seed once from the URL after the user (and thus role) resolves
  // (adjust during render, not in an effect).
  if (activeTab === null && authStatus === "authenticated") {
    const fromUrl = searchParams.get("tab") as ActiveTab | null;
    const remapped = fromUrl === "my-prompts" && isSuperAdmin ? "custom" : fromUrl;
    setActiveTab(remapped && allowedTabs.includes(remapped) ? remapped : defaultTab);
  }

  // Mirror the active tab to the URL for shareability (external-system update only).
  useEffect(() => {
    if (activeTab !== null && searchParams.get("tab") !== activeTab) {
      window.history.replaceState(null, "", `/ai-prompts/prompts/list?tab=${activeTab}`);
    }
  }, [activeTab, searchParams]);

  // ----------- Organization prompts state -----------
  const [orgPrompts, setOrgPrompts] = useState<Prompt[]>([]);
  const [orgLoading, setOrgLoading] = useState(true);
  const [orgError, setOrgError] = useState<string | null>(null);
  const [orgSearchTerm, setOrgSearchTerm] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "published">("all");
  const [orgCurrentPage, setOrgCurrentPage] = useState(1);
  const [orgPageSize, setOrgPageSize] = useState(() => getStoredPageSize(ORG_PAGE_SIZE_KEY, 20));

  // ----------- My prompts state -----------
  const [myPrompts, setMyPrompts] = useState<Prompt[]>([]);
  const [myLoading, setMyLoading] = useState(true);
  const [myError, setMyError] = useState<string | null>(null);
  const [mySearchTerm, setMySearchTerm] = useState("");
  const [myCurrentPage, setMyCurrentPage] = useState(1);
  const [myPageSize, setMyPageSize] = useState(() => getStoredPageSize(MY_PAGE_SIZE_KEY, 20));

  // ----------- Shared action state -----------
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [copyingId, setCopyingId] = useState<string | null>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);

  // ----------- Fetch org prompts -----------
  // Org-scoped prompts; admins also load pending-publish ones (shown inline,
  // surfaced via the status filter). Super-admins fetch all scopes - the
  // Custom tab filters by source.
  const fetchOrgPrompts = () => {
    setOrgLoading(true);
    const base = isSuperAdmin ? getPrompts() : getPrompts(undefined, "organization");
    const pending = isAdmin && !isSuperAdmin ? getPendingPublishPrompts() : Promise.resolve([]);
    Promise.all([base, pending])
      .then(([org, pend]) => {
        const seen = new Set(org.map((p) => p.id));
        setOrgPrompts([...org, ...pend.filter((p) => !seen.has(p.id))]);
        setOrgError(null);
      })
      .catch((err) => setOrgError(err instanceof Error ? err.message : "Failed to load prompts"))
      .finally(() => setOrgLoading(false));
  };

  // ----------- Fetch my prompts -----------
  const fetchMyPrompts = () => {
    setMyLoading(true);
    getPersonalPrompts()
      .then((data) => { setMyPrompts(data); setMyError(null); })
      .catch((err) => setMyError(err instanceof Error ? err.message : "Failed to load your prompts"))
      .finally(() => setMyLoading(false));
  };

  useEffect(() => {
    if (authStatus === "loading") return;
    // Defer so the setState inside the fetch functions isn't read as a synchronous
    // set within the effect body (cascading-render lint rule).
    void Promise.resolve().then(() => {
      fetchOrgPrompts();
      if (!isSuperAdmin) fetchMyPrompts();
    });
  }, [authStatus, isSuperAdmin]);

  // Count of prompts awaiting approval (drives the status filter label).
  const pendingCount = useMemo(
    () => orgPrompts.filter((t) => t.publish_status === "pending").length,
    [orgPrompts]
  );

  // ----------- Filter + paginate org prompts -----------
  const filteredOrgPrompts = useMemo(() => {
    return orgPrompts.filter((t) => {
      if (isSuperAdmin && t.source !== "custom" && t.source !== "super_admin") return false;
      if (categoryFilter && t.category !== categoryFilter) return false;
      if (statusFilter === "pending" && t.publish_status !== "pending") return false;
      if (statusFilter === "published" && t.publish_status === "pending") return false;
      if (orgSearchTerm) {
        const q = orgSearchTerm.toLowerCase();
        return (
          t.name.toLowerCase().includes(q) ||
          (t.description || "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [orgPrompts, orgSearchTerm, categoryFilter, statusFilter, isSuperAdmin]);

  const orgTotalPages = Math.ceil(filteredOrgPrompts.length / orgPageSize);
  const paginatedOrgPrompts = filteredOrgPrompts.slice(
    (orgCurrentPage - 1) * orgPageSize,
    orgCurrentPage * orgPageSize
  );

  // ----------- Filter + paginate my prompts -----------
  const filteredMyPrompts = useMemo(() => {
    if (!mySearchTerm) return myPrompts;
    const q = mySearchTerm.toLowerCase();
    return myPrompts.filter(
      (t) => t.name.toLowerCase().includes(q) || (t.description || "").toLowerCase().includes(q)
    );
  }, [myPrompts, mySearchTerm]);

  const myTotalPages = Math.ceil(filteredMyPrompts.length / myPageSize);
  const paginatedMyPrompts = filteredMyPrompts.slice(
    (myCurrentPage - 1) * myPageSize,
    myCurrentPage * myPageSize
  );

  // Reset org page when filters change (adjust during render, not in an effect).
  const orgFilterKey = `${orgSearchTerm}|${categoryFilter}|${statusFilter}`;
  const [prevOrgFilterKey, setPrevOrgFilterKey] = useState(orgFilterKey);
  if (orgFilterKey !== prevOrgFilterKey) {
    setPrevOrgFilterKey(orgFilterKey);
    setOrgCurrentPage(1);
  }

  // Reset my-prompts page when search changes (adjust during render, not in an effect).
  const [prevMySearchTerm, setPrevMySearchTerm] = useState(mySearchTerm);
  if (mySearchTerm !== prevMySearchTerm) {
    setPrevMySearchTerm(mySearchTerm);
    setMyCurrentPage(1);
  }

  // ----------- Handlers -----------
  const handleDelete = async (prompt: Prompt) => {
    if (!window.confirm(`Delete "${prompt.name}"? This cannot be undone.`)) return;
    setDeletingId(prompt.id);
    try {
      await deletePrompt(prompt.id);
      setOrgPrompts((prev) => prev.filter((t) => t.id !== prompt.id));
      setMyPrompts((prev) => prev.filter((t) => t.id !== prompt.id));
      toast({ title: "Prompt deleted", variant: "success" });
    } catch (err: unknown) {
      toast({ title: "Failed to delete prompt", description: err instanceof Error ? err.message : "Unknown error", variant: "destructive" });
    } finally {
      setDeletingId(null);
    }
  };

  const handleCopy = async (prompt: Prompt) => {
    setCopyingId(prompt.id);
    try {
      const copied = await copyPrompt(prompt.id);
      setMyPrompts((prev) => [...prev, copied]);
      toast({ title: `"${copied.name}" added to My Prompts`, variant: "success" });
    } catch (err: unknown) {
      toast({ title: "Failed to copy prompt", description: err instanceof Error ? err.message : "Unknown error", variant: "destructive" });
    } finally {
      setCopyingId(null);
    }
  };

  const handleRequestPublish = async (prompt: Prompt) => {
    setPublishingId(prompt.id);
    try {
      const updated = await requestPublishPrompt(prompt.id);
      setMyPrompts((prev) => prev.map((t) => (t.id === prompt.id ? updated : t)));
      toast({ title: "Publish request submitted", variant: "success" });
    } catch (err: unknown) {
      toast({ title: "Failed to request publish", description: err instanceof Error ? err.message : "Unknown error", variant: "destructive" });
    } finally {
      setPublishingId(null);
    }
  };

  const handleApprovePublish = async (prompt: Prompt) => {
    setPublishingId(prompt.id);
    try {
      const updated = await approvePublishPrompt(prompt.id);
      // Move from pending to org prompts
      setOrgPrompts((prev) => {
        const exists = prev.find((t) => t.id === updated.id);
        return exists ? prev.map((t) => (t.id === updated.id ? updated : t)) : [...prev, updated];
      });
      toast({ title: `"${updated.name}" published to organization`, variant: "success" });
    } catch (err: unknown) {
      toast({ title: "Failed to approve", description: err instanceof Error ? err.message : "Unknown error", variant: "destructive" });
    } finally {
      setPublishingId(null);
    }
  };

  const handleRejectPublish = async (prompt: Prompt) => {
    setPublishingId(prompt.id);
    try {
      const updated = await rejectPublishPrompt(prompt.id);
      setOrgPrompts((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
      toast({ title: `"${updated.name}" publish request rejected`, variant: "success" });
    } catch (err: unknown) {
      toast({ title: "Failed to reject", description: err instanceof Error ? err.message : "Unknown error", variant: "destructive" });
    } finally {
      setPublishingId(null);
    }
  };

  const handleSetVisibility = async (
    prompt: Prompt,
    visibility: "private" | "staging" | "public",
  ) => {
    try {
      const updated = await setPromptVisibility(prompt.id, visibility);
      setOrgPrompts((prev) => prev.map((t) => (t.id === prompt.id ? updated : t)));
      toast({ title: `"${updated.name}" is now ${visibility}`, variant: "success" });
    } catch (err: unknown) {
      toast({ title: "Failed to set visibility", description: err instanceof Error ? err.message : "Unknown error", variant: "destructive" });
    }
  };

  // ----------- Header controls -----------
  const headerControls =
    activeTab === "my-prompts" ||
    activeTab === "organization" ||
    activeTab === "custom" ? (
      <div className="flex items-center gap-2">
        <Link
          href="/ai-prompts/prompts/upload"
          className="btn-primary inline-flex items-center justify-center gap-2"
        >
          <Upload size={16} />
          Upload Prompt
        </Link>
        <Link
          href={withReturnTo("/ai-prompts/prompts/new", `/ai-prompts/prompts/list?tab=${activeTab}`)}
          className="btn-primary inline-flex items-center justify-center gap-2"
        >
          <Plus size={16} />
          New Prompt
        </Link>
      </div>
    ) : undefined;

  return (
    <ListPageLayout
      title="AI Prompts"
      description="Create and manage prompts for your workflows"
      actionButton={headerControls}
    >
      {/* Tabs */}
      <div className="border-b border-primary mb-6">
        <nav className="flex space-x-4" aria-label="AI Prompts tabs">
          {!isSuperAdmin && (
            <button
              type="button"
              onClick={() => setActiveTab("my-prompts")}
              className={`tab ${activeTab === "my-prompts" ? "tab-active" : "tab-inactive"}`}
            >
              My Prompts
            </button>
          )}
          <button
            type="button"
            onClick={() => setActiveTab(isSuperAdmin ? "custom" : "organization")}
            className={`tab ${(activeTab === "organization" || activeTab === "custom") ? "tab-active" : "tab-inactive"}`}
          >
            {isSuperAdmin ? "Custom" : "Organization"}
          </button>
          {isAdmin && (
            <button
              type="button"
              onClick={() => setActiveTab("marketplace")}
              className={`tab ${activeTab === "marketplace" ? "tab-active" : "tab-inactive"}`}
            >
              Marketplace
            </button>
          )}
        </nav>
      </div>

      {activeTab === "my-prompts" && !isSuperAdmin && (
        <PromptsMyTab
          loading={myLoading}
          error={myError}
          filteredPrompts={filteredMyPrompts}
          paginatedPrompts={paginatedMyPrompts}
          searchTerm={mySearchTerm}
          onSearchChange={setMySearchTerm}
          currentPage={myCurrentPage}
          totalPages={myTotalPages}
          pageSize={myPageSize}
          onPageChange={setMyCurrentPage}
          onPageSizeChange={(size) => { setMyPageSize(size); setMyCurrentPage(1); }}
          onDelete={handleDelete}
          deletingId={deletingId}
          onRequestPublish={handleRequestPublish}
          publishingId={publishingId}
          onRetry={fetchMyPrompts}
        />
      )}

      {(activeTab === "organization" || activeTab === "custom") && (
        <PromptsOrganizationTab
          loading={orgLoading}
          error={orgError}
          filteredPrompts={filteredOrgPrompts}
          paginatedPrompts={paginatedOrgPrompts}
          searchTerm={orgSearchTerm}
          onSearchChange={setOrgSearchTerm}
          categoryFilter={categoryFilter}
          onCategoryChange={setCategoryFilter}
          statusFilter={statusFilter}
          onStatusChange={setStatusFilter}
          pendingCount={pendingCount}
          currentPage={orgCurrentPage}
          totalPages={orgTotalPages}
          pageSize={orgPageSize}
          onPageChange={setOrgCurrentPage}
          onPageSizeChange={(size) => { setOrgPageSize(size); setOrgCurrentPage(1); }}
          isAdmin={isAdmin}
          isSuperAdmin={isSuperAdmin}
          onDelete={handleDelete}
          deletingId={deletingId}
          onCopy={handleCopy}
          copyingId={copyingId}
          onApprovePublish={handleApprovePublish}
          onRejectPublish={handleRejectPublish}
          publishingId={publishingId}
          onSetVisibility={isSuperAdmin ? handleSetVisibility : undefined}
          onRetry={fetchOrgPrompts}
        />
      )}

      {activeTab === "marketplace" && isAdmin && (
        <PromptsMarketplaceTab
          isSuperAdmin={isSuperAdmin}
          onPromptsChanged={fetchOrgPrompts}
        />
      )}
    </ListPageLayout>
  );
}

// ui/app/workflows/list/page.tsx

"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ListPageLayout } from "@/widgets/layout";
import { Plus } from "lucide-react";
import {
  getPersonalWorkflows,
  getOrganizationWorkflows,
  deleteWorkflow,
  updateWorkflow,
  importWorkflow,
  copyWorkflow,
  requestPublish,
  approvePublish,
  rejectPublish,
  getPendingPublish,
} from "@/shared/api";
import type { WorkflowResponse } from "@/shared/types/api";
import { useUser } from "@/entities/user";
import { useToast } from "@/features/toast";
import { getStoredPageSize } from "@/shared/lib/pagination";
import { listPageSizeKey } from "@/shared/lib/constants";
import { useWorkflowReadiness } from "./hooks/useWorkflowReadiness";
import { WorkflowsMyTab } from "./components/WorkflowsMyTab";
import { WorkflowsOrganizationTab } from "./components/WorkflowsOrganizationTab";
import { WorkflowsMarketplaceTab } from "./components/WorkflowsMarketplaceTab";

const PAGE_SIZE_KEY = listPageSizeKey('workflows');

export type WorkflowSortField = "name" | "status" | "updated_at";
export type SortDirection = "asc" | "desc";

type ActiveTab = "my-workflows" | "organization" | "custom" | "marketplace";

export default function WorkflowsListPage() {
  return (
    <Suspense>
      <WorkflowsListPageContent />
    </Suspense>
  );
}

function WorkflowsListPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, status: authStatus } = useUser();
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  const isSuperAdmin = user?.role === "super_admin";
  const { getIssues } = useWorkflowReadiness();

  // ----------- Tab state derived from URL (single source of truth) -----------
  const defaultTab: ActiveTab = isSuperAdmin ? "marketplace" : "organization";
  const tabParam = searchParams.get("tab") as ActiveTab | null;
  const allowedTabs: ActiveTab[] = isSuperAdmin
    ? ["custom", "marketplace"]
    : isAdmin
      ? ["my-workflows", "organization", "marketplace"]
      : ["my-workflows", "organization"];
  const requested: ActiveTab | null = tabParam
    ? tabParam
    : authStatus === "authenticated"
      ? defaultTab
      : null;
  const activeTab: ActiveTab | null = requested && allowedTabs.includes(requested) ? requested : (authStatus === "authenticated" ? defaultTab : null);

  // Sync URL when the resolved tab differs from what was requested
  useEffect(() => {
    if (authStatus !== "authenticated") return;
    if (tabParam && activeTab && activeTab !== tabParam) {
      router.replace(`/workflows/list?tab=${activeTab}`, { scroll: false });
    }
  }, [tabParam, activeTab, authStatus, router]);

  const setActiveTab = (tab: ActiveTab) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.replace(`/workflows/list?${params.toString()}`, { scroll: false });
  };

  // ----------- Workflows state -----------
  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(() =>
    getStoredPageSize(PAGE_SIZE_KEY, 25)
  );
  const [isImporting, setIsImporting] = useState(false);
  const [copyingId, setCopyingId] = useState<string | null>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [sortField, setSortField] = useState<WorkflowSortField>("updated_at");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // ----------- Pending publish state -----------
  const [pendingWorkflows, setPendingWorkflows] = useState<WorkflowResponse[]>([]);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);

  // ----------- Fetch workflows based on active tab -----------
  const fetchWorkflows = useCallback(async () => {
    if (authStatus === "loading" || !user) return;
    setLoading(true);
    setError(null);
    try {
      let data: WorkflowResponse[];
      if (activeTab === "my-workflows") {
        data = await getPersonalWorkflows();
      } else if (activeTab === "organization" || activeTab === "custom") {
        data = await getOrganizationWorkflows();
      } else {
        data = [];
      }
      setWorkflows(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load workflows");
    } finally {
      setLoading(false);
    }
  }, [activeTab, authStatus, user]);

  useEffect(() => {
    if (authStatus === "loading" || activeTab === null) return;
    if (activeTab === "my-workflows" || activeTab === "organization" || activeTab === "custom") {
      fetchWorkflows();
    }
  }, [activeTab, authStatus, fetchWorkflows]);

  // ----------- Fetch pending publish (admin only, org tab) -----------
  const fetchPendingPublish = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const data = await getPendingPublish();
      setPendingWorkflows(data);
    } catch {
      // Non-critical, silently fail
    }
  }, [isAdmin]);

  useEffect(() => {
    if (activeTab === "organization" && isAdmin && authStatus === "authenticated") {
      fetchPendingPublish();
    }
  }, [activeTab, isAdmin, authStatus, fetchPendingPublish]);

  // ----------- Filter + paginate workflows -----------
  const filteredWorkflows = useMemo(() => {
    let result = workflows;
    // Custom tab: exclude marketplace-installed workflows
    if (activeTab === "custom") {
      result = result.filter((w) => !w.client_metadata?.marketplace_id);
    }
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      result = result.filter(
        (w) =>
          w.name?.toLowerCase().includes(q) ||
          w.description?.toLowerCase().includes(q)
      );
    }
    result = [...result].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "name":
          cmp = (a.name || "").localeCompare(b.name || "");
          break;
        case "status":
          cmp = (a.status || "").localeCompare(b.status || "");
          break;
        case "updated_at":
          cmp = (a.updated_at || "").localeCompare(b.updated_at || "");
          break;
      }
      return sortDirection === "asc" ? cmp : -cmp;
    });
    return result;
  }, [workflows, searchTerm, sortField, sortDirection, activeTab]);

  const handleSort = (field: WorkflowSortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection(field === "updated_at" ? "desc" : "asc");
    }
  };

  const totalPages = Math.ceil(filteredWorkflows.length / pageSize);
  const paginatedWorkflows = filteredWorkflows.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, activeTab]);

  // ----------- Handlers: Workflow actions -----------

  const handleRun = (workflow: WorkflowResponse) => {
    // Route through the pre-run form page so users see the grouped input form
    // before the instance is created. PreRunForm at /run/[workflowId] handles
    // the form render, createInstance, startInstance, and the redirect to the
    // instance page in simple mode.
    router.push(`/run/${workflow.id}`);
  };

  const handleDelete = async (workflow: WorkflowResponse) => {
    if (!confirm("Are you sure you want to delete this workflow? This action cannot be undone.")) return;
    try {
      await deleteWorkflow(workflow.id);
      setWorkflows((prev) => prev.filter((w) => w.id !== workflow.id));
      toast({ title: "Workflow deleted", variant: "success" });
    } catch (error: unknown) {
      if (error instanceof Error && (error.message.includes("409") || error.message.toLowerCase().includes("inactive"))) {
        toast({ title: "Cannot delete", description: "Workflow must be inactive before deletion", variant: "destructive" });
      } else {
        toast({ title: "Failed to delete workflow", description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
      }
    }
  };

  const handleArchive = async (workflow: WorkflowResponse) => {
    if (!confirm("Are you sure you want to archive this workflow?")) return;
    try {
      await updateWorkflow(workflow.id, { status: "inactive" });
      setWorkflows((prev) =>
        prev.map((w) => (w.id === workflow.id ? { ...w, status: "inactive" } : w))
      );
      toast({ title: "Workflow archived", variant: "success" });
    } catch (error: unknown) {
      toast({ title: "Failed to archive workflow", description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
    }
  };

  const handleCopy = async (workflow: WorkflowResponse) => {
    setCopyingId(workflow.id);
    try {
      await copyWorkflow(workflow.id);
      toast({ title: `"${workflow.name}" copied to My Workflows`, variant: "success" });
      if (activeTab === "my-workflows") {
        fetchWorkflows();
      }
    } catch (error: unknown) {
      toast({ title: "Failed to copy workflow", description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
    } finally {
      setCopyingId(null);
    }
  };

  const handleRequestPublish = async (workflow: WorkflowResponse) => {
    setPublishingId(workflow.id);
    try {
      const updated = await requestPublish(workflow.id);
      setWorkflows((prev) =>
        prev.map((w) => (w.id === workflow.id ? { ...w, publish_status: updated.publish_status } : w))
      );
      toast({ title: "Publish request submitted", variant: "success" });
    } catch (error: unknown) {
      toast({ title: "Failed to request publish", description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
    } finally {
      setPublishingId(null);
    }
  };

  const handleApprovePublish = async (workflow: WorkflowResponse) => {
    setApprovingId(workflow.id);
    try {
      await approvePublish(workflow.id);
      setPendingWorkflows((prev) => prev.filter((w) => w.id !== workflow.id));
      toast({ title: `"${workflow.name}" published to Organization`, variant: "success" });
      fetchWorkflows();
    } catch (error: unknown) {
      toast({ title: "Failed to approve", description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
    } finally {
      setApprovingId(null);
    }
  };

  const handleRejectPublish = async (workflow: WorkflowResponse) => {
    setRejectingId(workflow.id);
    try {
      await rejectPublish(workflow.id);
      setPendingWorkflows((prev) => prev.filter((w) => w.id !== workflow.id));
      toast({ title: `"${workflow.name}" publish request rejected`, variant: "info" });
    } catch (error: unknown) {
      toast({ title: "Failed to reject", description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
    } finally {
      setRejectingId(null);
    }
  };

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsImporting(true);
    try {
      const result = await importWorkflow(file, user?.org_id);
      if (result.warnings && result.warnings.length > 0) {
        toast({ title: "Workflow imported with warnings", description: result.warnings.join(", "), variant: "info" });
      }
      fetchWorkflows();
      router.push(`/workflows/${result.workflow.id}/edit`);
    } catch (error: unknown) {
      toast({ title: "Failed to import workflow", description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
    } finally {
      setIsImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  // ----------- Header controls -----------
  const headerControls = (activeTab === "my-workflows" || activeTab === "organization" || activeTab === "custom") ? (
    <div className="flex items-center gap-4">
      <input type="file" ref={fileInputRef} onChange={handleImport} accept=".json" className="hidden" />
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={isImporting}
        className="btn-secondary inline-flex items-center justify-center shadow-sm text-sm disabled:opacity-50"
      >
        {isImporting ? "Importing..." : "Import"}
      </button>
      <Link
        href="/workflows/create"
        className="btn-primary inline-flex items-center justify-center gap-2"
      >
        <Plus size={16} />
        Create Workflow
      </Link>
    </div>
  ) : undefined;

  return (
    <ListPageLayout
      title="Workflows"
      description="View and manage your automated workflows"
      actionButton={headerControls}
    >
      {/* Tabs */}
      <div className="border-b border-primary mb-6">
        <nav className="flex space-x-4" aria-label="Workflow tabs">
          {!isSuperAdmin && (
            <button
              type="button"
              onClick={() => setActiveTab("my-workflows")}
              className={`tab ${activeTab === "my-workflows" ? "tab-active" : "tab-inactive"}`}
            >
              My Workflows
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

      {activeTab === "my-workflows" && !isSuperAdmin && (
        <WorkflowsMyTab
          loading={loading}
          error={error}
          filteredWorkflows={filteredWorkflows}
          paginatedWorkflows={paginatedWorkflows}
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          currentPage={currentPage}
          totalPages={totalPages}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          onPageSizeChange={handlePageSizeChange}
          onRun={handleRun}
          onDelete={handleDelete}
          onRequestPublish={handleRequestPublish}
          publishingId={publishingId}
          onRetry={fetchWorkflows}
          sortField={sortField}
          sortDirection={sortDirection}
          onSort={handleSort}
          getIssues={getIssues}
        />
      )}

      {(activeTab === "organization" || activeTab === "custom") && (
        <WorkflowsOrganizationTab
          loading={loading}
          error={error}
          filteredWorkflows={filteredWorkflows}
          paginatedWorkflows={paginatedWorkflows}
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          currentPage={currentPage}
          totalPages={totalPages}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          onPageSizeChange={handlePageSizeChange}
          isAdmin={isAdmin}
          isSuperAdmin={isSuperAdmin}
          onRun={handleRun}
          onDelete={handleDelete}
          onArchive={handleArchive}
          onCopy={handleCopy}
          copyingId={copyingId}
          pendingWorkflows={pendingWorkflows}
          onApprovePublish={handleApprovePublish}
          onRejectPublish={handleRejectPublish}
          approvingId={approvingId}
          rejectingId={rejectingId}
          onRetry={fetchWorkflows}
          sortField={sortField}
          sortDirection={sortDirection}
          onSort={handleSort}
          getIssues={getIssues}
        />
      )}

      {activeTab === "marketplace" && isAdmin && (
        <WorkflowsMarketplaceTab isSuperAdmin={isSuperAdmin} />
      )}
    </ListPageLayout>
  );
}
